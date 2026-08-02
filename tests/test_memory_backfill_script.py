from scripts.backfill_memory_from_sessions import backfill_sessions


def test_backfill_sessions_accumulates_capture_and_drain_results():
    class _Store:
        def load(self, session_id):
            return {"id": session_id}

    class _Pipeline:
        def capture(self, session, *, metadata):
            assert metadata["project_scope"] == "project"
            return 2

        def drain(self):
            return {"processed": 1, "local_processed": 1, "rejected": 0, "failed": 0, "queued": 0}

    result = backfill_sessions(_Store(), _Pipeline(), ["a", "b"], project_scope="project")

    assert result["sessions"] == 2
    assert result["chunks_enqueued"] == 4
    assert result["processed"] == 2
