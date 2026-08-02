import json

import pytest

from scripts import evaluate_memory_recall
from scripts.build_synthetic_memory_benchmark import build_fixture
from scripts.evaluate_memory_recall import load_cases
from scripts.prepare_memory_recall_cases import build_drafts


def test_memory_recall_script_loads_frozen_jsonl_cases(tmp_path):
    path = tmp_path / "frozen.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "case-1",
                "query": "RNA metadata",
                "relevant_memory_ids": ["mem-1"],
                "user_scope": "u-1",
                "project_scope": "p-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_cases(path)[0]["case_id"] == "case-1"


def test_memory_recall_script_enforces_target_thresholds(tmp_path, monkeypatch):
    cases = tmp_path / "frozen.jsonl"
    scorecard = tmp_path / "scorecard.json"
    cases.write_text(
        json.dumps(
            {
                "case_id": "case-1",
                "query": "RNA metadata",
                "relevant_memory_ids": ["mem-1"],
                "user_scope": "u-1",
                "project_scope": "p-1",
                "forbidden_memory_ids": ["mem-private"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    class _Store:
        def retrieve(self, query, *, limit, user_scope, project_scope):
            return [{"memory_id": "mem-1"}]

    monkeypatch.setattr(
        evaluate_memory_recall.PostgresLongTermMemoryStore,
        "from_environment",
        classmethod(lambda cls: _Store()),
    )

    assert evaluate_memory_recall.main([str(cases), "--output", str(scorecard)]) == 0
    assert json.loads(scorecard.read_text(encoding="utf-8"))["passed"] is True


def test_benchmark_drafts_do_not_copy_chunk_text_into_queries():
    drafts = build_drafts(
        [
            {
                "chunk_id": "chunk-1",
                "source_uri": "session://s/messages/0-1#sha256=abc",
                "content_sha256": "abc",
                "content": "A statement that must not become the query.",
            }
        ]
    )

    assert drafts[0]["query"] == ""
    assert drafts[0]["relevant_memory_ids"] == []
    assert "statement" not in drafts[0]


def test_memory_recall_script_rejects_unreviewed_draft(tmp_path):
    path = tmp_path / "draft.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "draft-1",
                "status": "draft",
                "query": "",
                "relevant_memory_ids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not frozen/ready"):
        load_cases(path)


def test_synthetic_qualification_fixture_is_versionable_and_scope_labelled():
    corpus, cases = build_fixture()

    assert len(corpus) == len(cases) == 200
    assert len({item["memory_id"] for item in corpus}) == 200
    assert all(item["status"] == "frozen" for item in cases)
    assert all(item["relevant_memory_ids"] for item in cases)
    assert {
        (item["user_scope"], item["project_scope"])
        for item in cases
    } == {("synthetic-user-a", "synthetic-memory-v1")}
