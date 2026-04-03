import json
import os
import asyncio
import aiohttp
from tqdm.asyncio import tqdm as async_tqdm
from typing import Iterable, Iterator, Dict, Any, List, Optional
from biocypher._logger import logger
from template_package.clients.pubmed_client import PubmedClient
from template_package.helpers.pubmed_query_builder import PubmedQueryBuilder

class PubmedAdapter:
    def __init__(self, gsmm_nodes: Iterable[tuple], email: Optional[str] = None, api_key: Optional[str] = None, retmax_per_query: int = 5, min_score: int = 3, organism_fallback: str = ""):
        self.gsmm_nodes = list(gsmm_nodes)
        self.client = PubmedClient(email=email, api_key=api_key)
        self.retmax_per_query = retmax_per_query
        self.min_score = min_score
        self.organism_fallback = organism_fallback
        self.cache_file = "data/pubmed_cache.json"
        self._links: List[tuple] = []

        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                if not isinstance(data, dict) or "articles" not in data:
                    self.cache_data = {"articles": {}, "searched_queries": [], "pmids_map": {}}
                else:
                    self.cache_data = data
                    if "pmids_map" not in self.cache_data: self.cache_data["pmids_map"] = {}
            except Exception:
                self.cache_data = {"articles": {}, "searched_queries": [], "pmids_map": {}}
        else:
            self.cache_data = {"articles": {}, "searched_queries": [], "pmids_map": {}}

    def save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache_data, f)

    def _score_match(self, props: Dict[str, Any], article: Dict[str, Any], abstract: str, matched_on: str) -> int:
        score = 0
        title = (article.get("title") or "").lower()
        abstract = (abstract or "").lower()

        # 1. Pontuação Textual (Contexto)
        name = (props.get("name") or "").lower()
        if name and name in title: score += 3
        if name and name in abstract: score += 2

        organism = (props.get("organism") or self.organism_fallback or "").lower()
        if organism and (organism in title or organism in abstract): score += 2

        if any(x in abstract for x in ["metabolism", "metabolic", "flux", "pathway", "enzyme"]): score += 1

        # 2. Bónus de Identificador (Apenas se o contexto fizer sentido)
        if matched_on in {"uniprot", "ncbigene", "ecogene", "chebi", "hmdb", "kegg_compound", "kegg_reaction", "rhea", "biocyc"}:
            if score > 0:
                # Só damos os 5 pontos extra se o texto já tiver alguma relação (organismo, nome ou contexto)
                score += 5
            else:
                # Se o score for 0, é apenas um número perdido num DOI ou página. Damos 0 ou 1.
                score += 1 

        return score

    def _clean_text(self, text: str) -> str:
        if not text: return ""
        # Substitui aspas simples por duplas e remove enters/tabs que partem o CSV
        return text.replace("'", '"').replace("\n", " ").replace("\r", "").replace("\t", " ")

    # --- FUNÇÕES ASSÍNCRONAS ---
    async def _run_phase1_searches(self, queries_to_run):
        sem = asyncio.Semaphore(9) # Máximo de 10 chamadas concorrentes à API
        
        async def fetch(session, node_id, matched_on, query, pbar):
            async with sem:
                await asyncio.sleep(0.05) # Respeita limite da NCBI API
                pmids = await self.client.search_pubmed(session, query, self.retmax_per_query)
                pbar.update(1)
                return (node_id, matched_on, query, pmids)

        connector = aiohttp.TCPConnector(limit=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            pbar = async_tqdm(total=len(queries_to_run), desc="Phase 1: Async PubMed Search")
            tasks = [fetch(session, n_id, m_on, q, pbar) for n_id, m_on, q in queries_to_run]
            results = await asyncio.gather(*tasks)
            pbar.close()
            return results

    async def _run_phase2_downloads(self, pmid_batches):
        sem = asyncio.Semaphore(5) # Downloads pesados, máximo 5 em simultâneo
        
        async def download_batch(session, batch, pbar):
            async with sem:
                data = await self.client.fetch_metadata_batch(session, batch)
                pbar.update(1)
                return data

        connector = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            pbar = async_tqdm(total=len(pmid_batches), desc="Phase 2: Async Metadata Download")
            tasks = [download_batch(session, b, pbar) for b in pmid_batches]
            results = await asyncio.gather(*tasks)
            pbar.close()
            
            final_data = {}
            for r in results: final_data.update(r)
            return final_data

    # --- FUNÇÃO PRINCIPAL ---
    def get_nodes(self) -> Iterator[tuple]:
        queries_to_run = []
        node_query_map = {}
        
        # 1. Preparar o que precisa de ser pesquisado
        for node_id, label, props in self.gsmm_nodes:
            if label not in {"model", "model_gene", "model_reaction", "model_metabolite"}: continue
            node_query_map[node_id] = []
            queries = PubmedQueryBuilder.build_queries(node_id, label, props, self.organism_fallback)
            for matched_on, query in queries:
                if query not in self.cache_data["searched_queries"]:
                    queries_to_run.append((node_id, matched_on, query))

        # 2. Correr pesquisas assíncronas (Phase 1)
        if queries_to_run:
            search_results = asyncio.run(self._run_phase1_searches(queries_to_run))
            for n_id, m_on, q, pmids in search_results:
                if pmids: self.cache_data["pmids_map"][q] = pmids
                self.cache_data["searched_queries"].append(q)
            self.save_cache()

        # 3. Reunir todos os PMIDs necessários
        all_needed_pmids = set()
        for node_id, label, props in self.gsmm_nodes:
            if label not in {"model", "model_gene", "model_reaction", "model_metabolite"}: continue
            queries = PubmedQueryBuilder.build_queries(node_id, label, props, self.organism_fallback)
            for matched_on, query in queries:
                pmids = self.cache_data["pmids_map"].get(query, [])
                for pmid in pmids:
                    node_query_map[node_id].append((pmid, matched_on, query))
                    if pmid not in self.cache_data["articles"]:
                        all_needed_pmids.add(pmid)

        # 4. Correr downloads de abstracts em massa assíncronos (Phase 2)
        if all_needed_pmids:
            pmid_list = list(all_needed_pmids)
            batches = [pmid_list[i:i+100] for i in range(0, len(pmid_list), 100)]
            download_results = asyncio.run(self._run_phase2_downloads(batches))
            self.cache_data["articles"].update(download_results)
            self.save_cache()

        # 5. Criar nós e gerar (Yield) para o BioCypher (Phase 3)
        seen_pmids = set()
        for node_id, label, props in self.gsmm_nodes:
            findings = node_query_map.get(node_id, [])
            for pmid, matched_on, query in findings:
                article = self.cache_data["articles"].get(pmid)
                if not article: continue
                
                score = self._score_match(props, article, article["abstract"], matched_on)
                if score >= self.min_score:
                    # Guardamos o score, a query e o tipo de match na aresta
                    edge_properties = {
                        "score": score,
                        "query": query,
                        "matched_on": matched_on
                    }
                    self._links.append((
                        f"{node_id}_mentions_{pmid}", 
                        node_id, 
                        f"PMID:{pmid}", 
                        "biomedical_entity_has_literature", 
                        edge_properties
                    ))
                    
                    if pmid not in seen_pmids:
                        seen_pmids.add(pmid)
                        clean_article = {
                            "pmid": pmid,
                            "title": self._clean_text(article.get("title", "")),
                            "journal": self._clean_text(article.get("journal", "")),
                            "pub_date": article.get("pub_date", ""),
                            # Trocamos o | por vírgula para não confundir o separador de arrays do Neo4j
                            "authors": self._clean_text(article.get("authors", "").replace("|", ", ")),
                            "abstract": self._clean_text(article.get("abstract", "")),
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                        }
                        yield (f"PMID:{pmid}", "pubmed_article", clean_article)

    def get_edges(self) -> Iterator[tuple]:
        if not self._links and self.gsmm_nodes:
            list(self.get_nodes())
        yield from self._links