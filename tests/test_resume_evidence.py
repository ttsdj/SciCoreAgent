import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_resume_metrics_artifact_matches_documented_claims():
    metrics_path = REPO_ROOT / "artifacts" / "resume-metrics-v1.json"
    harness_path = REPO_ROOT / "artifacts" / "harness-regression-v2.json"
    resume_path = REPO_ROOT / "docs" / "resume" / "biocoreagent_resume_star.md"
    memory_scorecard_path = REPO_ROOT / "artifacts" / "memory-recall-synthetic-v1.json"
    graph_scorecard_path = REPO_ROOT / "artifacts" / "research-graph-curated-v1.json"

    assert metrics_path.is_file()
    assert harness_path.is_file()
    assert resume_path.is_file()
    assert memory_scorecard_path.is_file()
    assert graph_scorecard_path.is_file()

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    harness = json.loads(harness_path.read_text(encoding="utf-8"))
    resume = resume_path.read_text(encoding="utf-8")
    memory_scorecard = json.loads(memory_scorecard_path.read_text(encoding="utf-8"))
    graph_scorecard = json.loads(graph_scorecard_path.read_text(encoding="utf-8"))

    assert harness["summary"]["passed"] == 14
    assert harness["summary"]["pass_rate"] == 1.0
    assert harness["summary"]["within_budget_rate"] == 1.0
    assert harness["summary"]["verifier_pass_rate"] == 1.0

    assert metrics["memory"]["query_count"] == 40
    assert metrics["memory"]["hit_rate_at_10"] == 1.0
    assert metrics["memory"]["mrr_at_10"] == 1.0
    assert memory_scorecard["query_count"] == 200
    assert memory_scorecard["hit_rate_at_10"] >= 0.994
    assert memory_scorecard["mrr_at_10"] >= 0.67
    assert memory_scorecard["scope_leakage_rate"] == 0.0
    assert memory_scorecard["benchmark_class"] == "synthetic_engineering_qualification"
    assert memory_scorecard["embedding_backend"].startswith("sentence_transformers:")
    assert graph_scorecard["case_count"] == 8
    assert graph_scorecard["entity"]["f1"] == 1.0
    assert graph_scorecard["event_relation"]["f1"] == 1.0
    assert graph_scorecard["effective_time_accuracy"] == 1.0
    assert graph_scorecard["evidence_coverage"] == 1.0
    assert graph_scorecard["total_score"] == 100.0
    assert graph_scorecard["hard_gates_passed"] is True

    assert metrics["context"]["case_count"] == 15
    assert metrics["context"]["average_raw_chars"] == 26928
    assert metrics["context"]["average_prompt_chars"] == 1795.33
    assert metrics["context"]["average_compression_ratio"] == 0.929541
    assert metrics["context"]["request_retention_rate"] == 1.0
    assert metrics["context"]["latest_evidence_retention_rate"] == 1.0
    assert metrics["context"]["budget_compliance_rate"] == 1.0

    assert metrics["multiagent"]["suite"] == "eight_worker_scheduler_v2_three_run_median"
    assert metrics["multiagent"]["speedup"] >= 2.0
    assert metrics["multiagent"]["lifecycle_state_count"] == 9
    assert metrics["multiagent"]["degradation_levels"] == 3

    assert metrics["bixbench_verified50"]["initial"]["passed"] == 22
    assert metrics["bixbench_verified50"]["best"]["passed"] == 38

    for claim in (
        "14/14",
        "26,928",
        "1,795",
        "92.95%",
        "至少 2.0",
        "44%",
        "76%",
    ):
        assert claim in resume


def test_resume_document_states_material_claim_boundaries():
    resume = (
        REPO_ROOT
        / "docs"
        / "resume"
        / "biocoreagent_resume_star.md"
    ).read_text(encoding="utf-8")

    assert "当前 Postgres 实现将 embedding 保存为 JSONB" in resume
    assert "当前 100%/1.000 来自 200 条冻结合成工程资格集" in resume
    assert "官方外部 LLM judge 未运行" in resume
    assert "44% 是 BioCoreAgent 初版" in resume
