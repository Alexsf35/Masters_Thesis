import requests
import time
import urllib3
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class PubmedClient:
    BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key
        # Usar uma sessão para manter a ligação ativa (evita RemoteDisconnected)
        self.session = requests.Session()

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        params = {"tool": "biocypher_adapter", **extra}
        if self.email: params["email"] = self.email
        if self.api_key: params["api_key"] = self.api_key
        return params

    def search_pubmed(self, query: str, retmax: int = 5) -> List[str]:
        url = f"{self.BASE}/esearch.fcgi"
        params = self._params({"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax})
        time.sleep(0.1) # Respeitar API Key
        r = self.session.get(url, params=params, timeout=30, verify=False)
        r.raise_for_status()
        return r.json().get("esearchresult", {}).get("idlist", [])

    def fetch_metadata_batch(self, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Descarrega Summaries e Abstracts em massa (Batch)"""
        if not pmids: return {}
        
        results = {}
        # 1. Buscar Summaries em massa
        url_sum = f"{self.BASE}/esummary.fcgi"
        params_sum = self._params({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
        r_sum = self.session.get(url_sum, params=params_sum, timeout=60, verify=False)
        sum_data = r_sum.json().get("result", {})

        # 2. Buscar Abstracts em massa (XML)
        url_abs = f"{self.BASE}/efetch.fcgi"
        params_abs = self._params({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
        r_abs = self.session.get(url_abs, params=params_abs, timeout=60, verify=False)
        
        root = ET.fromstring(r_abs.text)
        for article in root.findall(".//PubmedArticle"):
            pmid = article.find(".//PMID").text
            abs_parts = article.findall(".//Abstract/AbstractText")
            abstract = " ".join("".join(x.itertext()).strip() for x in abs_parts)
            
            summary = sum_data.get(pmid, {})
            results[pmid] = {
                "title": summary.get("title", ""),
                "journal": summary.get("fulljournalname", ""),
                "pub_date": summary.get("pubdate", ""),
                "authors": "|".join(a.get("name", "") for a in summary.get("authors", [])),
                "abstract": abstract
            }
        return results