from scripts.review_memory_recall_drafts import parse_source_uri


def test_review_script_parses_immutable_session_source_uri():
    assert parse_source_uri("session://session-1/messages/2-5#sha256=" + "f" * 64) == ("session-1", 2, 5)
