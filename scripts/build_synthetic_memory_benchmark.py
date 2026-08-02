"""Build a frozen, synthetic cross-session memory retrieval qualification set.

This set validates named-entity retrieval, scope isolation, and ranking.  It is
an engineering acceptance set, not evidence of open-domain semantic quality.
The output directory must be new so a scored fixture cannot be silently
rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


GENES = (
    "TP53", "EGFR", "BRCA1", "MYC", "KRAS", "PTEN", "APOE", "STAT3",
    "VEGFA", "CDKN2A", "IL6", "TNF", "MAPK1", "AKT1", "ESR1", "AR",
    "HIF1A", "MTOR", "CXCL8", "GAPDH",
)
TISSUES = (
    "liver", "heart", "kidney", "lung", "brain",
    "muscle", "spleen", "pancreas", "colon", "skin",
)
METHODS = (
    "DESeq2", "edgeR", "limma-voom", "Salmon", "STAR",
    "Scanpy", "Seurat", "MaxQuant", "MSstats", "GSEA",
)


def build_fixture():
    corpus = []
    cases = []
    for index, (gene, tissue) in enumerate(
        (pair for gene in GENES for pair in ((gene, tissue) for tissue in TISSUES)),
        start=1,
    ):
        method = METHODS[(index * 7) % len(METHODS)]
        threshold = 0.01 + (index % 5) * 0.01
        statement = (
            f"For the {tissue} project, the retained {gene} workflow uses "
            f"{method} with validation threshold {threshold:.2f}."
        )
        memory_id = f"synthetic_mem_{index:04d}"
        source_sha256 = hashlib.sha256(statement.encode("utf-8")).hexdigest()
        user_scope = "synthetic-user-a"
        project_scope = "synthetic-memory-v1"
        corpus.append(
            {
                "memory_id": memory_id,
                "memory_type": "decision",
                "statement": statement,
                "tags": [gene, tissue, method, "synthetic-qualification"],
                "user_scope": user_scope,
                "project_scope": project_scope,
                "distiller_version": "synthetic_fixture_v1",
                "evidence": {
                    "source_uri": (
                        f"session://synthetic-memory-{index:04d}/messages/0-0"
                        f"#sha256={source_sha256}"
                    ),
                    "source_sha256": source_sha256,
                    "session_id": f"synthetic-memory-{index:04d}",
                    "start_message_index": 0,
                    "end_message_index": 0,
                },
            }
        )
        cases.append(
            {
                "case_id": f"synthetic_query_{index:04d}",
                "status": "frozen",
                "query": (
                    f"What workflow and validation setting did we retain for "
                    f"{gene} in the {tissue} project?"
                ),
                "relevant_memory_ids": [memory_id],
                "forbidden_memory_ids": [],
                "user_scope": user_scope,
                "project_scope": project_scope,
                "fixture_class": "synthetic_named_entity_cross_session",
            }
        )
    return corpus, cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="benchmarks/memory_recall/synthetic-v1",
    )
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir)
    corpus_path = output_dir / "corpus.jsonl"
    cases_path = output_dir / "frozen.jsonl"
    if corpus_path.exists() or cases_path.exists():
        parser.error("fixture already exists; choose a new versioned output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    corpus, cases = build_fixture()
    corpus_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in corpus),
        encoding="utf-8",
    )
    cases_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in cases),
        encoding="utf-8",
    )
    readme = output_dir / "README.md"
    readme.write_text(
        "# Synthetic memory qualification v1\n\n"
        "This frozen 200-query set tests cross-session named-entity retrieval, "
        "ranking, and scope filters. It is synthetic engineering evidence and "
        "must not be described as open-domain semantic-QA performance.\n",
        encoding="utf-8",
    )
    print(json.dumps({"corpus": len(corpus), "cases": len(cases)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
