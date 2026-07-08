"""Persistent asyncio-based multi-agent orchestration for BiocoreagentV2.0."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


TERMINAL_STATES = {"completed", "failed", "cancelled", "blocked"}
VALID_ROLES = {"explorer", "planner", "executor", "verifier", "bio_worker"}


@dataclass
class AgentJob:
    job_id: str
    task: str
    role: str
    status: str = "queued"
    team_id: str = ""
    name: str = ""
    dependencies: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    attempt: int = 0
    max_retries: int = 1
    session_id: str = ""
    run_id: str = ""
    result: str = ""
    error: str = ""
    cancel_requested: bool = False


@dataclass
class AgentTeam:
    team_id: str
    objective: str
    job_ids: list[str]
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    synthesis: str = ""


class JsonStateStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve() / ".biocoreagent" / "multiagent"
        self.jobs_dir = self.root / "jobs"
        self.teams_dir = self.root / "teams"
        self.messages_dir = self.root / "messages"
        for path in (self.jobs_dir, self.teams_dir, self.messages_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def save_job(self, job: AgentJob) -> None:
        self._atomic_json(self.jobs_dir / f"{job.job_id}.json", asdict(job))

    def load_job(self, job_id: str) -> AgentJob | None:
        data = self._read_json(self.jobs_dir / f"{job_id}.json")
        return AgentJob(**data) if data else None

    def list_jobs(self) -> list[AgentJob]:
        jobs = []
        for path in self.jobs_dir.glob("job_*.json"):
            data = self._read_json(path)
            if data:
                jobs.append(AgentJob(**data))
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    def save_team(self, team: AgentTeam) -> None:
        self._atomic_json(self.teams_dir / f"{team.team_id}.json", asdict(team))

    def load_team(self, team_id: str) -> AgentTeam | None:
        data = self._read_json(self.teams_dir / f"{team_id}.json")
        return AgentTeam(**data) if data else None

    def append_message(self, team_id: str, message: dict[str, Any]) -> None:
        path = self.messages_dir / f"{team_id}.jsonl"
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(message, ensure_ascii=False) + "\n")

    def list_messages(self, team_id: str, recipient: str = "") -> list[dict[str, Any]]:
        path = self.messages_dir / f"{team_id}.jsonl"
        if not path.exists():
            return []
        messages = []
        with self._lock:
            for line in path.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if not recipient or item.get("recipient") in {"", "*", recipient}:
                    messages.append(item)
        return messages

    def _atomic_json(self, path: Path, data: dict[str, Any]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(path)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with self._lock:
            return json.loads(path.read_text(encoding="utf-8"))


class AsyncMultiAgentOrchestrator:
    """Central scheduler for independent Pico runs.

    The scheduler owns lifecycle and persistence. Each worker owns its own
    model client, session, task state, checkpoint, trace, and role tool policy.
    """

    def __init__(
        self,
        workspace_root: str | Path,
        agent_factory: Callable[[str, bool], Any],
        max_concurrency: int = 4,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.agent_factory = agent_factory
        self.store = JsonStateStore(self.workspace_root)
        self.max_concurrency = max(1, int(max_concurrency))
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="biocore-orchestrator", daemon=True)
        self._tasks: dict[str, Future] = {}
        self._agents: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._thread.start()
        self._semaphore = self._submit(self._make_semaphore()).result(timeout=5)
        self._recover_interrupted_jobs()

    @property
    def tool_names(self) -> set[str]:
        return {
            "agent_start", "agent_status", "agent_cancel", "agent_retry",
            "agent_team_start", "agent_team_status", "agent_team_cancel",
            "agent_message",
        }

    async def _make_semaphore(self):
        return asyncio.Semaphore(self.max_concurrency)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coroutine) -> Future:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def start_job(
        self,
        task: str,
        role: str = "explorer",
        *,
        team_id: str = "",
        name: str = "",
        dependencies: list[str] | None = None,
        max_retries: int = 1,
    ) -> AgentJob:
        if role not in VALID_ROLES:
            raise ValueError(f"unknown role: {role}")
        if not task.strip():
            raise ValueError("task must not be empty")
        job = AgentJob(
            job_id="job_" + uuid.uuid4().hex[:12],
            task=task.strip(),
            role=role,
            team_id=team_id,
            name=name or role,
            dependencies=list(dependencies or []),
            max_retries=max(0, int(max_retries)),
        )
        self.store.save_job(job)
        future = self._submit(self._schedule_job(job.job_id))
        with self._lock:
            self._tasks[job.job_id] = future
        return job

    async def _schedule_job(self, job_id: str) -> None:
        while True:
            job = self.store.load_job(job_id)
            if job is None or job.cancel_requested:
                if job is not None:
                    self._finish_job(job, "cancelled", error="cancel requested before execution")
                return
            dependencies = [self.store.load_job(dep) for dep in job.dependencies]
            if any(dep is None or dep.status in {"failed", "cancelled", "blocked"} for dep in dependencies):
                self._finish_job(job, "blocked", error="dependency did not complete successfully")
                return
            if all(dep.status == "completed" for dep in dependencies):
                break
            await asyncio.sleep(0.1)

        async with self._semaphore:
            await asyncio.to_thread(self._execute_job, job_id)

    def _execute_job(self, job_id: str) -> None:
        job = self.store.load_job(job_id)
        if job is None:
            return
        if job.cancel_requested:
            self._finish_job(job, "cancelled", error="cancel requested")
            return

        job.status = "running"
        job.started_at = time.time()
        job.attempt += 1
        self.store.save_job(job)
        try:
            agent = self.agent_factory(job.role, True)
            with self._lock:
                self._agents[job_id] = agent
            dependency_context = self._dependency_context(job)
            message_context = self._message_context(job)
            prompt = (
                f"Team objective task assigned to agent '{job.name}' ({job.role}).\n"
                f"{job.task}\n{dependency_context}{message_context}\n"
                "Return observed facts, actions taken, evidence paths, missing information, and recommended next steps."
            )
            result = agent.ask(prompt)
            job = self.store.load_job(job_id) or job
            if job.cancel_requested:
                self._finish_job(job, "cancelled", error="cancel requested while worker was running")
                return
            job.session_id = str(agent.session.get("id", ""))
            if agent.current_task_state is not None:
                job.run_id = agent.current_task_state.run_id
            self._finish_job(job, "completed", result=result)
        except Exception as exc:
            job = self.store.load_job(job_id) or job
            if job.attempt <= job.max_retries and not job.cancel_requested:
                job.status = "queued"
                job.error = str(exc)
                self.store.save_job(job)
                future = self._submit(self._schedule_job(job_id))
                with self._lock:
                    self._tasks[job_id] = future
            else:
                self._finish_job(job, "failed", error=str(exc))
        finally:
            with self._lock:
                self._agents.pop(job_id, None)

    def _finish_job(self, job: AgentJob, status: str, result: str = "", error: str = "") -> None:
        job.status = status
        job.completed_at = time.time()
        job.result = result
        job.error = error
        self.store.save_job(job)

    def start_team(self, objective: str, agents: list[dict[str, Any]]) -> AgentTeam:
        if not objective.strip():
            raise ValueError("objective must not be empty")
        if not 2 <= len(agents) <= 12:
            raise ValueError("a team requires 2-12 agents")

        names = self._validate_team_specs(agents)
        team_id = "team_" + uuid.uuid4().hex[:12]
        name_to_id = {
            name: "job_" + uuid.uuid4().hex[:12]
            for name in names
        }
        jobs = []
        for index, spec in enumerate(agents, start=1):
            role = str(spec.get("role", "explorer"))
            if role not in VALID_ROLES:
                raise ValueError(f"unknown role: {role}")
            name = str(spec.get("name") or f"{role}_{index}")
            dependencies = [name_to_id[item] for item in spec.get("depends_on", [])]
            job = AgentJob(
                job_id=name_to_id[name],
                task=str(spec.get("task") or spec.get("focus") or objective),
                role=role,
                team_id=team_id,
                name=name,
                dependencies=dependencies,
                max_retries=max(0, int(spec.get("max_retries", 1))),
            )
            self.store.save_job(job)
            jobs.append(job)

        team = AgentTeam(team_id=team_id, objective=objective.strip(), job_ids=[job.job_id for job in jobs])
        self.store.save_team(team)
        for job in jobs:
            with self._lock:
                self._tasks[job.job_id] = self._submit(self._schedule_job(job.job_id))
        self._submit(self._monitor_team(team_id))
        return team

    @staticmethod
    def _validate_team_specs(agents: list[dict[str, Any]]) -> list[str]:
        names = [
            str(spec.get("name") or f"{spec.get('role', 'explorer')}_{index}")
            for index, spec in enumerate(agents, start=1)
        ]
        if len(set(names)) != len(names):
            raise ValueError("team member names must be unique")
        known = set(names)
        graph = {}
        for name, spec in zip(names, agents):
            dependencies = [str(item) for item in spec.get("depends_on", [])]
            unknown = sorted(set(dependencies) - known)
            if unknown:
                raise ValueError(f"unknown dependencies for {name}: {', '.join(unknown)}")
            if name in dependencies:
                raise ValueError(f"team dependency cycle includes {name}")
            graph[name] = dependencies

        visiting = set()
        visited = set()

        def visit(name):
            if name in visiting:
                raise ValueError(f"team dependency cycle includes {name}")
            if name in visited:
                return
            visiting.add(name)
            for dependency in graph[name]:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in names:
            visit(name)
        return names

    async def _monitor_team(self, team_id: str) -> None:
        while True:
            team = self.store.load_team(team_id)
            if team is None:
                return
            jobs = [self.store.load_job(job_id) for job_id in team.job_ids]
            jobs = [job for job in jobs if job is not None]
            if jobs and all(job.status in TERMINAL_STATES for job in jobs):
                team.status = "failed" if any(job.status in {"failed", "blocked"} for job in jobs) else (
                    "cancelled" if any(job.status == "cancelled" for job in jobs) else "completed"
                )
                team.completed_at = time.time()
                team.synthesis = self._synthesize(team, jobs)
                self.store.save_team(team)
                return
            team.status = "running"
            self.store.save_team(team)
            await asyncio.sleep(0.2)

    def cancel_job(self, job_id: str) -> bool:
        job = self.store.load_job(job_id)
        if job is None or job.status in TERMINAL_STATES:
            return False
        job.cancel_requested = True
        self.store.save_job(job)
        future = self._tasks.get(job_id)
        if job.status == "queued" and future:
            future.cancel()
            self._finish_job(job, "cancelled", error="cancel requested")
        return True

    def cancel_team(self, team_id: str) -> bool:
        team = self.store.load_team(team_id)
        if team is None or team.status in TERMINAL_STATES:
            return False
        changed = False
        for job_id in team.job_ids:
            changed = self.cancel_job(job_id) or changed
        return changed

    def retry_job(self, job_id: str) -> AgentJob:
        old = self.store.load_job(job_id)
        if old is None:
            raise ValueError(f"unknown job: {job_id}")
        if old.status not in TERMINAL_STATES:
            raise ValueError("only terminal jobs can be retried")
        return self.start_job(
            old.task,
            old.role,
            team_id=old.team_id,
            name=old.name,
            dependencies=old.dependencies,
            max_retries=old.max_retries,
        )

    def send_message(self, team_id: str, sender: str, recipient: str, content: str) -> dict[str, Any]:
        if self.store.load_team(team_id) is None:
            raise ValueError(f"unknown team: {team_id}")
        message = {
            "message_id": "msg_" + uuid.uuid4().hex[:12],
            "team_id": team_id,
            "sender": sender,
            "recipient": recipient or "*",
            "content": content,
            "created_at": time.time(),
        }
        self.store.append_message(team_id, message)
        return message

    def job_status(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.load_job(job_id)
        return asdict(job) if job else None

    def team_status(self, team_id: str) -> dict[str, Any] | None:
        team = self.store.load_team(team_id)
        if team is None:
            return None
        data = asdict(team)
        data["jobs"] = [self.job_status(job_id) for job_id in team.job_ids]
        data["messages"] = self.store.list_messages(team_id)
        return data

    def wait_for_job(self, job_id: str, timeout: float = 30) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.job_status(job_id)
            if status is None or status["status"] in TERMINAL_STATES:
                return status
            time.sleep(0.05)
        return self.job_status(job_id)

    def wait_for_team(self, team_id: str, timeout: float = 60) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.team_status(team_id)
            if status is None or status["status"] in TERMINAL_STATES:
                return status
            time.sleep(0.05)
        return self.team_status(team_id)

    def _dependency_context(self, job: AgentJob) -> str:
        if not job.dependencies:
            return ""
        lines = ["\nCompleted dependency results:"]
        for dep_id in job.dependencies:
            dep = self.store.load_job(dep_id)
            if dep:
                lines.append(f"- {dep.name} ({dep.role}): {dep.result[:3000]}")
        return "\n".join(lines)

    def _message_context(self, job: AgentJob) -> str:
        if not job.team_id:
            return ""
        messages = self.store.list_messages(job.team_id, recipient=job.name)
        if not messages:
            return ""
        return "\nTeam messages:\n" + "\n".join(
            f"- from {item['sender']}: {item['content']}" for item in messages[-10:]
        )

    @staticmethod
    def _synthesize(team: AgentTeam, jobs: list[AgentJob]) -> str:
        lines = [f"# Team synthesis: {team.objective}", ""]
        for job in jobs:
            lines.extend([
                f"## {job.name} ({job.role}) [{job.status}]",
                job.result or job.error or "(no result)",
                "",
            ])
        lines.append("## Decision boundary")
        if any(job.status != "completed" for job in jobs):
            lines.append("The team has incomplete or failed work; do not treat the objective as verified.")
        else:
            lines.append("All assigned agents completed. Final claims still require artifact-level verification.")
        return "\n".join(lines)

    def _recover_interrupted_jobs(self) -> None:
        for job in self.store.list_jobs():
            if job.status == "running":
                job.status = "failed"
                job.completed_at = time.time()
                job.error = "orchestrator restarted while job was running; retry explicitly"
                self.store.save_job(job)

    def tool_registry(self, parent_agent) -> dict[str, dict[str, Any]]:
        return {
            "agent_start": self._spec(
                {"task": "string", "role": "string=optional", "max_retries": "integer=optional"},
                "Start an independent background agent run.",
                lambda args: json.dumps(asdict(self.start_job(**args)), ensure_ascii=False),
                risky=True,
            ),
            "agent_status": self._spec(
                {"job_id": "string"},
                "Read durable status for a background agent.",
                lambda args: json.dumps(self.job_status(args["job_id"]), ensure_ascii=False, indent=2),
            ),
            "agent_cancel": self._spec(
                {"job_id": "string"},
                "Request cancellation of a queued or running agent.",
                lambda args: json.dumps({"cancelled": self.cancel_job(args["job_id"])}),
                risky=True,
            ),
            "agent_retry": self._spec(
                {"job_id": "string"},
                "Create a new attempt for a terminal agent job.",
                lambda args: json.dumps(asdict(self.retry_job(args["job_id"])), ensure_ascii=False),
                risky=True,
            ),
            "agent_team_start": self._spec(
                {"objective": "string", "agents": "array"},
                "Start a concurrent or dependency-ordered role-based agent team.",
                lambda args: json.dumps(asdict(self.start_team(**args)), ensure_ascii=False),
                risky=True,
            ),
            "agent_team_status": self._spec(
                {"team_id": "string"},
                "Read team, member, synthesis, and message state.",
                lambda args: json.dumps(self.team_status(args["team_id"]), ensure_ascii=False, indent=2),
            ),
            "agent_team_cancel": self._spec(
                {"team_id": "string"},
                "Request cancellation of every non-terminal member of a team.",
                lambda args: json.dumps({"cancel_requested": self.cancel_team(args["team_id"])}),
                risky=True,
            ),
            "agent_message": self._spec(
                {"team_id": "string", "sender": "string", "recipient": "string", "content": "string"},
                "Persist a message for another member of an agent team.",
                lambda args: json.dumps(self.send_message(**args), ensure_ascii=False),
            ),
        }

    @staticmethod
    def _spec(schema, description, runner, risky=False):
        return {"schema": schema, "description": description, "risky": risky, "run": runner}

    def validate_tool(self, name: str, args: dict[str, Any]) -> None:
        required = {
            "agent_start": {"task"},
            "agent_status": {"job_id"},
            "agent_cancel": {"job_id"},
            "agent_retry": {"job_id"},
            "agent_team_start": {"objective", "agents"},
            "agent_team_status": {"team_id"},
            "agent_team_cancel": {"team_id"},
            "agent_message": {"team_id", "sender", "recipient", "content"},
        }[name]
        missing = sorted(key for key in required if args.get(key) in (None, ""))
        if missing:
            raise ValueError(f"missing required arguments: {', '.join(missing)}")

    def shutdown(self) -> None:
        try:
            self._submit(self._cancel_pending_tasks()).result(timeout=5)
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _cancel_pending_tasks(self) -> None:
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
