#!/usr/bin/env python3

from pathlib import Path
from biocypher import BioCypher

from template_package.adapters.gsmm_adapter import GSMMAdapter
from template_package.adapters.pubmed_adapter import PubmedAdapter


def main():

    # --------------------------------------------------
    # 1) Input model
    # --------------------------------------------------
    sbml_fp = Path("models/e_coli_core.xml").resolve()

    if not sbml_fp.exists():
        raise FileNotFoundError(f"SBML file not found: {sbml_fp}")

    print(f"[info] Using model: {sbml_fp}")

    # --------------------------------------------------
    # 2) Initialize BioCypher
    # --------------------------------------------------
    bc = BioCypher()

    # --------------------------------------------------
    # 3) GSMM Adapter
    # --------------------------------------------------
    adapter_gsmm = GSMMAdapter(
        sbml_paths=[str(sbml_fp)],
        provenance={
            "source": "BiGG",
            "model": "e_coli_core",
        },
    )

    # Materialize nodes ONCE (important for reuse)
    gsmm_nodes = list(adapter_gsmm.get_nodes())

    print(f"[info] GSMM nodes: {len(gsmm_nodes)}")
    print(f"[info] GSMM edges: {adapter_gsmm.get_edge_count()}")

    # --------------------------------------------------
    # 4) PubMed Adapter (literature enrichment)
    # --------------------------------------------------
    adapter_pubmed = PubmedAdapter(
        gsmm_nodes=gsmm_nodes,
        email="alexsaferreira3355@gmail.com",   # REQUIRED by NCBI (put your real email)
        api_key="92383e9a27af9daad9be4827c9d78aacd509",                   # optional but recommended
        retmax_per_query=1,               # keep small to avoid explosion
        min_score=4,                      # filter weak matches
        organism_fallback="Escherichia coli",
    )

    # --------------------------------------------------
    # 5) Write graph
    # --------------------------------------------------

    # GSMM layer
    bc.write_nodes(iter(gsmm_nodes))
    bc.write_edges(adapter_gsmm.get_edges())

    # PubMed layer
    bc.write_nodes(adapter_pubmed.get_nodes())
    bc.write_edges(adapter_pubmed.get_edges())

    # --------------------------------------------------
    # 6) Finalize
    # --------------------------------------------------
    bc.write_import_call()
    #bc.summary()

    print("[ok] Graph creation completed.")


if __name__ == "__main__":
    main()