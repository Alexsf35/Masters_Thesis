import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from biocypher._logger import logger

class PubmedClient:
    BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key

    def _params(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        params = {"tool": "biocypher_adapter", **extra}
        if self.email: params["email"] = self.email
        if self.api_key: params["api_key"] = self.api_key
        return params

    async def search_pubmed(self, session: aiohttp.ClientSession, query: str, retmax: int = 5) -> List[str]:
        url = f"{self.BASE}/esearch.fcgi"
        params = self._params({"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax})
        
        # Sistema de Retries: Tenta até 3 vezes se o servidor bloquear
        for attempt in range(3):
            try:
                async with session.get(url, params=params, ssl=False) as response:
                    if response.status in (429, 500, 502, 503, 504):
                        # Se o servidor estiver sobrecarregado, espera (1s, 2s, 4s) e tenta de novo
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    response.raise_for_status()
                    data = await response.json()
                    return data.get("esearchresult", {}).get("idlist", [])
            except Exception as e:
                if attempt == 2:
                    logger.warning(f"Search query failed completely after 3 attempts: {query} | Error: {e}")
                await asyncio.sleep(2 ** attempt)
        return []

    async def fetch_metadata_batch(self, session: aiohttp.ClientSession, pmids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not pmids: return {}
        results = {}
        
        url_sum = f"{self.BASE}/esummary.fcgi"
        params_sum = self._params({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
        url_abs = f"{self.BASE}/efetch.fcgi"
        params_abs = self._params({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"})
        
        for attempt in range(3):
            try:
                async with session.get(url_sum, params=params_sum, ssl=False) as r_sum:
                    if r_sum.status != 200:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    sum_json = await r_sum.json()
                    sum_data = sum_json.get("result", {})
                    
                async with session.get(url_abs, params=params_abs, ssl=False) as r_abs:
                    if r_abs.status != 200:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    xml_text = await r_abs.text()
                    root = ET.fromstring(xml_text)
                    
                    for article in root.findall(".//PubmedArticle"):
                        pmid_el = article.find(".//PMID")
                        if pmid_el is None: continue
                        pmid = pmid_el.text
                        
                        abs_parts = article.findall(".//Abstract/AbstractText")
                        abstract = " ".join("".join(x.itertext()).strip() for x in abs_parts if x is not None)
                        
                        summary = sum_data.get(pmid, {})
                        if isinstance(summary, dict):
                            results[pmid] = {
                                "title": summary.get("title", ""),
                                "journal": summary.get("fulljournalname", ""),
                                "pub_date": summary.get("pubdate", ""),
                                "authors": "|".join(a.get("name", "") for a in summary.get("authors", []) if isinstance(a, dict)),
                                "abstract": abstract
                            }
                return results # Se chegou aqui com sucesso, sai do loop de tentativas
            except Exception as e:
                if attempt == 2:
                    logger.warning(f"Batch fetch failed completely after 3 attempts. Error: {e}")
                await asyncio.sleep(2 ** attempt)
        return results