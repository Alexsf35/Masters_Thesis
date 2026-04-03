import os
import gzip
import logging
from typing import Iterable, Iterator, Dict, Any, Set

logger = logging.getLogger(__name__)

class StringAdapter:
    def __init__(self, gsmm_nodes: Iterable[tuple], tax_id: str = "511145", min_score: int = 900
    ):
        self.gsmm_nodes = list(gsmm_nodes)
        self.tax_id = tax_id
        self.min_score = min_score
        
        self.data_dir = "data/string"
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.files = {
            "info": f"{self.tax_id}.protein.info.v12.0.txt.gz",
            "links": f"{self.tax_id}.protein.links.full.v12.0.txt.gz",
            "terms": f"{self.tax_id}.protein.enrichment.terms.v12.0.txt.gz"
        }
        
        self.allowed_string_ids: Set[str] = set()
        self.valid_string_ids: Set[str] = set()
        self._gsmm_to_string_map: Dict[str, str] = {}

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        return text.replace("'", "").replace('"', "").replace("\n", " ").replace("\r", "").replace("\t", " ")

    def _download_if_missing(self, file_key: str):
        filename = self.files[file_key]
        filepath = os.path.join(self.data_dir, filename)
        
        if not os.path.exists(filepath):
            logger.error(f"Missing required STRING DB file: {filename}")
            raise FileNotFoundError(f"Missing {filename} in {self.data_dir}. Please download it manually.")
            
        return filepath

    def _match_gsmm_to_string(self):
        """Maps GSMM model_gene nodes to STRING protein IDs and defines allowed IDs."""
        for node_id, label, props in self.gsmm_nodes:
            if label != "model_gene":
                continue
                
            locus_tag = props.get("refseq_locus_tag") or props.get("refseq_old_locus_tag")
            
            if not locus_tag:
                if ":" not in str(node_id):
                    locus_tag = str(node_id)
                else:
                    continue 
            
            expected_string_id = f"{self.tax_id}.{locus_tag}"
            self._gsmm_to_string_map[node_id] = expected_string_id
            self.allowed_string_ids.add(expected_string_id) # Registar como proteína permitida

    def get_nodes(self) -> Iterator[tuple]:
        self._match_gsmm_to_string()
        
        # 1. Parse Protein Info
        info_path = self._download_if_missing("info")
        logger.info("Parsing STRING protein info (Filtered by GSMM genes)...")
        
        with gzip.open(info_path, 'rt', encoding='utf-8') as f:
            next(f)
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 4: continue
                
                protein_id = parts[0]
                
                if protein_id not in self.allowed_string_ids:
                    continue

                preferred_name = self._clean_text(parts[1])
                protein_size = parts[2]
                annotation = self._clean_text(parts[3])
                
                self.valid_string_ids.add(protein_id)
                
                yield (
                    protein_id,
                    "protein",
                    {
                        "name": preferred_name,
                        "size": protein_size,
                        "annotation": annotation,
                        "tax_id": self.tax_id
                    }
                )
                
        # 2. Parse Enrichment Terms
        terms_path = self._download_if_missing("terms")
        logger.info("Parsing STRING enrichment terms (Filtered by valid proteins)...")
        
        seen_terms = set()
        with gzip.open(terms_path, 'rt', encoding='utf-8') as f:
            next(f)
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 4: continue
                
                string_id = parts[0]
                category = self._clean_text(parts[1])
                term_id = parts[2] 
                description = self._clean_text(parts[3])
                
                if string_id not in self.valid_string_ids:
                    continue
                
                if term_id not in seen_terms:
                    seen_terms.add(term_id)
                    yield (
                        term_id,
                        "functional_term",
                        {
                            "name": description,
                            "category": category
                        }
                    )

    def get_edges(self) -> Iterator[tuple]:
        if not self.valid_string_ids:
            list(self.get_nodes())
            
        logger.info("Yielding GSMM to STRING mapping edges...")
        for gsmm_id, string_id in self._gsmm_to_string_map.items():
            if string_id in self.valid_string_ids:
                yield (
                    f"{gsmm_id}_maps_to_{string_id}",
                    gsmm_id,
                    string_id,
                    "encodes",
                    {"source": "identifier_match"}
                )

        links_path = self._download_if_missing("links")
        logger.info("Parsing STRING protein links (Filtered)...")

        seen_interactions = set()
        
        with gzip.open(links_path, 'rt', encoding='utf-8') as f:
            next(f)
            for line in f:
                parts = line.strip().split(' ')
                if len(parts) < 16: continue
                
                p1 = parts[0]
                p2 = parts[1]
                combined_score = int(parts[15])
                
                if combined_score >= self.min_score:
                    if p1 in self.valid_string_ids and p2 in self.valid_string_ids:

                        interaction_key = tuple(sorted([p1, p2]))
                        if interaction_key in seen_interactions:
                            continue
                        
                        seen_interactions.add(interaction_key)

                        yield (
                            f"{p1}_interacts_{p2}",
                            p1,
                            p2,
                            "interacts_with",
                            {
                                "neighborhood": int(parts[2]),
                                "neighborhood_transferred": int(parts[3]),
                                "fusion": int(parts[4]),
                                "cooccurence": int(parts[5]),
                                "homology": int(parts[6]),
                                "coexpression": int(parts[7]),
                                "coexpression_transferred": int(parts[8]),
                                "experiments": int(parts[9]),
                                "experiments_transferred": int(parts[10]),
                                "database": int(parts[11]),
                                "database_transferred": int(parts[12]),
                                "textmining": int(parts[13]),
                                "textmining_transferred": int(parts[14]),
                                "combined_score": combined_score
                            }
                        )
                        
        terms_path = self._download_if_missing("terms")
        logger.info("Parsing STRING protein-term associations (Filtered)...")
        
        with gzip.open(terms_path, 'rt', encoding='utf-8') as f:
            next(f)
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 4: continue
                
                string_id = parts[0]
                term_id = parts[2]
                
                if string_id in self.valid_string_ids:
                    yield (
                        f"{string_id}_has_term_{term_id}",
                        string_id,
                        term_id,
                        "has_functional_annotation",
                        {}
                    )