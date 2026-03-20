from typing import Dict, Any, List, Tuple

class PubmedQueryBuilder:
    @staticmethod
    def build_queries(node_id: str, label: str, props: Dict[str, Any], organism: str = "") -> List[Tuple[str, str]]:
        queries = []

        if label == "model_gene":
            for key in ["uniprot", "ncbigene", "ecogene", "biocyc"]:
                value = props.get(key)
                if value:
                    queries.append((key, f'"{value}"[All Fields]'))
            if props.get("name"):
                q = f'("{props["name"]}"[Title/Abstract])'
                if organism:
                    q += f' AND ("{organism}"[Title/Abstract] OR "{organism}"[MeSH Terms])'
                queries.append(("name", q))

        elif label == "model_reaction":
            if props.get("ec_code"):
                queries.append(("ec_code", f'"EC {props["ec_code"]}"[Title/Abstract]'))
            for key in ["rhea", "kegg_reaction", "biocyc"]:
                value = props.get(key)
                if value:
                    queries.append((key, f'"{value}"[All Fields]'))
            if props.get("name"):
                q = f'("{props["name"]}"[Title/Abstract])'
                if organism:
                    q += f' AND "{organism}"[Title/Abstract]'
                queries.append(("name", q))

        elif label == "model_metabolite":
            for key in ["chebi", "hmdb", "kegg_compound", "pubchem_compound", "biocyc"]:
                value = props.get(key)
                if value:
                    queries.append((key, f'"{value}"[All Fields]'))
            if props.get("name"):
                queries.append(("name", f'("{props["name"]}"[Title/Abstract]) AND metabolism[Title/Abstract]'))

        elif label == "model":
            if props.get("name"):
                queries.append(("name", f'"{props["name"]}"[All Fields]'))
            if props.get("organism"):
                queries.append(("organism_model", f'"genome-scale metabolic model"[Title/Abstract] AND "{props["organism"]}"[Title/Abstract]'))

        return queries