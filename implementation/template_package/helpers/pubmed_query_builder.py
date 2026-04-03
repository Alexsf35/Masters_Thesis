from typing import Dict, Any, List, Tuple

class PubmedQueryBuilder:
    @staticmethod
    def build_queries(node_id: str, label: str, props: Dict[str, Any], organism: str = "") -> List[Tuple[str, str]]:
        queries = []

        if label == "model_gene":
            for key in ["uniprot", "ncbigene", "ecogene", "biocyc"]:
                value = props.get(key)
                if value:
                    q = f'"{value}"[All Fields]'
                    # Se tivermos o organismo, obrigamos a que ele apareça no texto
                    if organism:
                        q += f' AND ("{organism}"[Title/Abstract] OR "{organism}"[MeSH Terms])'
                    # Se for o NCBI Gene (que é sempre um número puro) e não houver organismo, exigimos contexto genético
                    elif key == "ncbigene" or str(value).isdigit():
                        q += f' AND (gene[Title/Abstract] OR protein[Title/Abstract] OR genome[Title/Abstract])'
                    queries.append((key, q))
            
            if props.get("name"):
                q = f'("{props["name"]}"[Title/Abstract])'
                if organism:
                    q += f' AND ("{organism}"[Title/Abstract] OR "{organism}"[MeSH Terms])'
                queries.append(("name", q))

        elif label == "model_reaction":
            if props.get("ec_code"):
                q = f'"EC {props["ec_code"]}"[Title/Abstract]'
                if organism: q += f' AND "{organism}"[Title/Abstract]'
                queries.append(("ec_code", q))
                
            for key in ["rhea", "kegg_reaction", "biocyc"]:
                value = props.get(key)
                if value:
                    q = f'"{value}"[All Fields]'
                    if organism:
                        q += f' AND "{organism}"[Title/Abstract]'
                    elif str(value).isdigit():
                        q += f' AND (reaction[Title/Abstract] OR enzyme[Title/Abstract] OR metabolism[Title/Abstract])'
                    queries.append((key, q))
                    
            if props.get("name"):
                q = f'("{props["name"]}"[Title/Abstract])'
                if organism:
                    q += f' AND "{organism}"[Title/Abstract]'
                queries.append(("name", q))

        elif label == "model_metabolite":
            for key in ["chebi", "hmdb", "kegg_compound", "pubchem_compound", "biocyc"]:
                value = props.get(key)
                if value:
                    q = f'"{value}"[All Fields]'
                    if organism:
                        q += f' AND "{organism}"[Title/Abstract]'
                    # Compostos químicos precisam sempre de contexto metabólico para evitar falsos positivos na química pura
                    q += f' AND (metabolite[Title/Abstract] OR metabolism[Title/Abstract] OR pathway[Title/Abstract])'
                    queries.append((key, q))
                    
            if props.get("name"):
                q = f'("{props["name"]}"[Title/Abstract]) AND metabolism[Title/Abstract]'
                if organism:
                    q += f' AND "{organism}"[Title/Abstract]'
                queries.append(("name", q))

        elif label == "model":
            if props.get("name"):
                queries.append(("name", f'"{props["name"]}"[All Fields]'))
            if props.get("organism"):
                queries.append(("organism_model", f'"genome-scale metabolic model"[Title/Abstract] AND "{props["organism"]}"[Title/Abstract]'))

        return queries