import json
import os
from typing import Iterable, Iterator, Dict, Any, List, Optional
from biocypher._logger import logger
from tqdm import tqdm
from template_package.clients.pubmed_client import PubmedClient
from template_package.helpers.pubmed_query_builder import PubmedQueryBuilder

class PubmedAdapter:
    def __init__(
        self,
        gsmm_nodes: Iterable[tuple],
        email: Optional[str] = None,
        api_key: Optional[str] = None,
        retmax_per_query: int = 5,
        min_score: int = 3,
        organism_fallback: str = "",
    ):
        self.gsmm_nodes = list(gsmm_nodes)
        self.client = PubmedClient(email=email, api_key=api_key)
        self.retmax_per_query = retmax_per_query
        self.min_score = min_score
        self.organism_fallback = organism_fallback

        self.cache_file = "data/pubmed_cache.json"
        self._links: List[tuple] = []

        # Inicialização da Cache
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                if not isinstance(data, dict) or "articles" not in data:
                    self.cache_data = {"articles": data if isinstance(data, dict) else {}, "searched_queries": []}
                else:
                    self.cache_data = data
            except Exception:
                self.cache_data = {"articles": {}, "searched_queries": []}
        else:
            self.cache_data = {"articles": {}, "searched_queries": []}

    @property
    def _article_cache(self):
        return self.cache_data["articles"]

    def save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache_data, f)

    def _score_match(self, props: Dict[str, Any], article: Dict[str, Any], abstract: str, matched_on: str) -> int:
        score = 0
        title = (article.get("title") or "").lower()
        abstract = (abstract or "").lower()

        # Bonus por identificadores fortes
        if matched_on in {"uniprot", "ncbigene", "ecogene", "chebi", "hmdb", "kegg_compound", "kegg_reaction", "rhea", "biocyc"}:
            score += 5

        name = (props.get("name") or "").lower()
        if name and name in title:
            score += 3
        if name and name in abstract:
            score += 2

        organism = (props.get("organism") or self.organism_fallback or "").lower()
        if organism and (organism in title or organism in abstract):
            score += 2

        if any(x in abstract for x in ["metabolism", "metabolic", "flux", "pathway", "enzyme"]):
            score += 1

        return score

    def get_nodes(self) -> Iterator[tuple]:
        # 1. FASE DE PROCURA (Rápida)
        node_query_map = {} # node_id -> List[pmids]
        all_found_pmids = set()

        pbar = tqdm(self.gsmm_nodes, desc="Phase 1: Searching PMIDs")
        for node_id, label, props in pbar:
            if label not in {"model", "model_gene", "model_reaction", "model_metabolite"}: continue
            
            queries = PubmedQueryBuilder.build_queries(node_id, label, props, self.organism_fallback)
            node_query_map[node_id] = []

            for matched_on, query in queries:
                if query in self.cache_data["searched_queries"]: continue
                
                try:
                    pmids = self.client.search_pubmed(query, retmax=self.retmax_per_query)
                    for pmid in pmids:
                        node_query_map[node_id].append((pmid, matched_on, query))
                        if pmid not in self.cache_data["articles"]:
                            all_found_pmids.add(pmid)
                    self.cache_data["searched_queries"].append(query)
                except Exception as e:
                    logger.warning(f"Search failed for {node_id}: {e}")
            
            if len(self.cache_data["searched_queries"]) % 10 == 0: self.save_cache()

        # 2. FASE DE DOWNLOAD EM MASSA (Batch)
        if all_found_pmids:
            pmid_list = list(all_found_pmids)
            desc = "Phase 2: Downloading Metadata"
            for i in tqdm(range(0, len(pmid_list), 100), desc=desc):
                batch = pmid_list[i:i+100]
                new_articles = self.client.fetch_metadata_batch(batch)
                self.cache_data["articles"].update(new_articles)
                self.save_cache()

        # 3. FASE DE YIELD (Gerar nós e links)
        for node_id, findings in node_query_map.items():
            props_orig = next(p for n, l, p in self.gsmm_nodes if n == node_id)
            for pmid, matched_on, query in findings:
                article = self.cache_data["articles"].get(pmid)
                if not article: continue
                
                score = self._score_match(props_orig, article, article["abstract"], matched_on)
                if score >= self.min_score:
                    # Gerar link
                    self._links.append((f"{node_id}_{pmid}", node_id, f"PMID:{pmid}", 
                                      "biomedical_entity_has_literature", {"score": score}))
                    yield (f"PMID:{pmid}", "pubmed_article", article)

    def get_edges(self) -> Iterator[tuple]:
        # Garante que os nós foram processados para popular os links
        if not self._links and self.gsmm_nodes:
            # Isto é apenas um fallback se get_edges for chamado antes de get_nodes
            list(self.get_nodes())
        yield from self._links