import time
from pathlib import Path

from pico.providers.clients import FakeModelClient
from pico.run_store import RunStore
from pico.session_store import SessionStore
from pico.workspace import WorkspaceContext

from biocoreagent.orchestrator import AsyncMultiAgentOrchestrator, JsonStateStore
from biocoreagent.runtime import BioPico


def build_factory(tmp_path: Path, prompts: dict[str, list[str]]):
    def factory(role: str, worker: bool):
        client = FakeModelClient([f"<final>{role} completed</final>"])
        prompts.setdefault(role, []).append(client)
        return BioPico(
            model_client=client,
            workspace=WorkspaceContext.build(tmp_path),
            session_store=SessionStore(tmp_path / ".biocoreagent" / "sessions"),
            run_store=RunStore(tmp_path / ".biocoreagent" / "runs"),
            approval_policy="auto",
            role=role,
            orchestrator=None,
            allow_orchestration=not worker,
        )

    return factory


def test_team_runs_independent_agents_and_persists_state(tmp_path):
    clients = {}
    manager = AsyncMultiAgentOrchestrator(
        tmp_path,
        build_factory(tmp_path, clients),
        max_concurrency=2,
    )
    try:
        team = manager.start_team(
            "Review RNA-seq inputs",
            [
                {"name": "inspect", "role": "explorer", "task": "Inspect files"},
                {"name": "plan", "role": "planner", "task": "Plan analysis"},
            ],
        )
        status = manager.wait_for_team(team.team_id, timeout=10)

        assert status["status"] == "completed"
        assert {job["role"] for job in status["jobs"]} == {"explorer", "planner"}
        assert all(job["session_id"] for job in status["jobs"])
        assert len({job["session_id"] for job in status["jobs"]}) == 2
        assert len({job["run_id"] for job in status["jobs"]}) == 2
        assert "All assigned agents completed" in status["synthesis"]

        reloaded = JsonStateStore(tmp_path)
        assert reloaded.load_team(team.team_id).status == "completed"
        assert all(reloaded.load_job(job_id).status == "completed" for job_id in team.job_ids)
    finally:
        manager.shutdown()


def test_dag_dependency_result_is_injected_into_downstream_prompt(tmp_path):
    clients = {}
    manager = AsyncMultiAgentOrchestrator(tmp_path, build_factory(tmp_path, clients), max_concurrency=2)
    try:
        team = manager.start_team(
            "Validate analysis",
            [
                {"name": "inspect", "role": "explorer", "task": "Inspect"},
                {
                    "name": "verify",
                    "role": "verifier",
                    "task": "Verify",
                    "depends_on": ["inspect"],
                },
            ],
        )
        status = manager.wait_for_team(team.team_id, timeout=10)

        assert status["status"] == "completed"
        verifier_prompt = clients["verifier"][0].prompts[0]
        assert "Completed dependency results" in verifier_prompt
        assert "explorer completed" in verifier_prompt
    finally:
        manager.shutdown()


def test_message_bus_is_durable_and_recipient_scoped(tmp_path):
    clients = {}
    manager = AsyncMultiAgentOrchestrator(tmp_path, build_factory(tmp_path, clients))
    try:
        team = manager.start_team(
            "Message test",
            [
                {"name": "one", "role": "explorer", "task": "One"},
                {"name": "two", "role": "planner", "task": "Two"},
            ],
        )
        sent = manager.send_message(team.team_id, "one", "two", "check sample labels")
        messages = manager.store.list_messages(team.team_id, recipient="two")

        assert messages == [sent]
        assert manager.store.list_messages(team.team_id, recipient="one") == []
        manager.wait_for_team(team.team_id, timeout=5)
    finally:
        manager.shutdown()


def test_cancel_queued_job_and_retry_terminal_job(tmp_path):
    class SlowClient(FakeModelClient):
        def complete(self, prompt, max_new_tokens, **kwargs):
            time.sleep(0.3)
            return super().complete(prompt, max_new_tokens, **kwargs)

    def factory(role, worker):
        return BioPico(
            model_client=SlowClient([f"<final>{role} done</final>"]),
            workspace=WorkspaceContext.build(tmp_path),
            session_store=SessionStore(tmp_path / ".biocoreagent" / "sessions"),
            run_store=RunStore(tmp_path / ".biocoreagent" / "runs"),
            approval_policy="auto",
            role=role,
            allow_orchestration=False,
        )

    manager = AsyncMultiAgentOrchestrator(tmp_path, factory, max_concurrency=1)
    try:
        first = manager.start_job("occupy worker", "explorer")
        second = manager.start_job("cancel me", "planner")
        assert manager.cancel_job(second.job_id)
        cancelled = manager.wait_for_job(second.job_id, timeout=5)
        assert cancelled["status"] == "cancelled"

        retried = manager.retry_job(second.job_id)
        done = manager.wait_for_job(retried.job_id, timeout=5)
        assert done["status"] == "completed"
        assert retried.job_id != second.job_id
        assert manager.wait_for_job(first.job_id, timeout=5)["status"] == "completed"
    finally:
        manager.shutdown()


def test_team_rejects_unknown_and_cyclic_dependencies_before_persisting(tmp_path):
    manager = AsyncMultiAgentOrchestrator(tmp_path, build_factory(tmp_path, {}))
    try:
        try:
            manager.start_team(
                "bad",
                [
                    {"name": "one", "role": "explorer", "depends_on": ["missing"]},
                    {"name": "two", "role": "planner"},
                ],
            )
            raise AssertionError("unknown dependency was accepted")
        except ValueError as exc:
            assert "unknown dependencies" in str(exc)

        try:
            manager.start_team(
                "cycle",
                [
                    {"name": "one", "role": "explorer", "depends_on": ["two"]},
                    {"name": "two", "role": "planner", "depends_on": ["one"]},
                ],
            )
            raise AssertionError("dependency cycle was accepted")
        except ValueError as exc:
            assert "cycle" in str(exc)
        assert manager.store.list_jobs() == []
    finally:
        manager.shutdown()


def test_root_orchestration_tools_require_approval(tmp_path):
    clients = {}
    holder = {}

    def factory(role, worker):
        return BioPico(
            model_client=FakeModelClient(["<final>done</final>"]),
            workspace=WorkspaceContext.build(tmp_path),
            session_store=SessionStore(tmp_path / ".biocoreagent" / "sessions"),
            run_store=RunStore(tmp_path / ".biocoreagent" / "runs"),
            approval_policy="auto",
            role=role,
            orchestrator=holder.get("manager"),
            allow_orchestration=not worker,
        )

    manager = AsyncMultiAgentOrchestrator(tmp_path, factory)
    holder["manager"] = manager
    try:
        root = factory("executor", False)
        assert root.tools["agent_start"]["risky"] is True
        assert root.tools["agent_team_start"]["risky"] is True
        worker = factory("bio_worker", True)
        assert "agent_start" not in worker.tools
        assert "agent_team_start" not in worker.tools
    finally:
        manager.shutdown()
