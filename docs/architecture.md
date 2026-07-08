# BiocoreagentV2.0 Architecture

## Design decision

BiocoreagentV2.0 is one harness with domain extensions, not two nested agents.
Pico owns the control plane. BioCoreAgent owns biological capabilities.

```text
User / CLI
    |
    v
BioPico (composition boundary)
    |
    +-- Pico control plane
    |   +-- AgentLoop
    |   +-- ContextManager
    |   +-- LayeredMemory
    |   +-- ToolExecutor
    |   +-- TaskState + Checkpoint
    |   +-- RunStore + redaction
    |
    +-- BioCore domain plane
    |   +-- sequence/sample/count inspection
    |   +-- RNA-seq/statistical tools
    |   +-- workflow/experiment planning
    |   +-- Skill + Wiki + RAG + knowledge base
    |   +-- MCP client tools
    |   +-- SSH/HPC boundary
    |
    +-- Multi-agent orchestration plane
        +-- central asyncio scheduler
        +-- persistent Job and Team state
        +-- independent BioPico worker runs
        +-- role tool capabilities
        +-- DAG dependency scheduling
        +-- durable message bus
        +-- retry/cancellation/restart handling
```

## Why Pico remains the kernel

Pico's tool execution is a single choke point. Validation, approval, workspace
snapshots, result metadata, memory updates, checkpoints, trace events, and run
reports happen around the tool call. A domain tool cannot become an alternative
execution path.

Its context manager also separates stable prefix, working memory, relevant
memory, history, and the current request. This is retained instead of the old
BioCore three-threshold message mutation strategy.

## Domain tool adaptation

`DomainToolAdapter` translates each BioCore JSON Schema into Pico's prompt tool
description. At execution time it:

1. validates required and unknown arguments;
2. resolves local path arguments under the active workspace;
3. leaves remote SSH paths to the remote sandbox policy;
4. invokes the original BioCore tool;
5. returns the observation to Pico's `ToolExecutor`.

Generic BioCore file, shell, context, and legacy agent tools are excluded.
Their Pico equivalents or the v2 orchestrator are authoritative.

External MCP tools are loaded once by the CLI and adapted dynamically. They are
always treated as risky because an external server's side effects cannot be
inferred reliably from its schema.

## Multi-agent lifecycle

Each job has its own:

- model client;
- BioPico instance;
- role-restricted tool registry;
- session and layered memory;
- task/run identifiers;
- trace, report, and checkpoints.

The central scheduler controls concurrency and dependency readiness. It does
not merge worker conversation histories. Dependencies are passed downstream as
bounded result context.

```text
queued -> running -> completed
   |         |          |
   |         +------> failed -> explicit retry creates a new job
   +---------------> cancelled
   +---------------> blocked (dependency failure)
```

Cancellation is immediate for queued jobs and cooperative for an already
running blocking provider request. Python cannot safely terminate an arbitrary
in-flight thread. Production hard cancellation therefore requires running each
worker in a separate process or container.

## Role security

- `explorer`: read-only repository and evidence inspection.
- `planner`: read-only inspection plus workflow and experiment planning.
- `executor`: complete capability set, subject to approvals.
- `verifier`: tests, hashes, and validation-oriented bio tools.
- `bio_worker`: analysis and SSH execution without team-control authority.

Workers cannot start nested teams. Only the root executor receives
orchestration tools, preserving centralized ownership.

## Persistence and recovery

```text
.biocoreagent/
├── sessions/
├── runs/
└── multiagent/
    ├── jobs/job_*.json
    ├── teams/team_*.json
    └── messages/team_*.jsonl
```

Writes use temporary-file replacement. After restart, a job previously marked
`running` becomes `failed` with an interruption reason. It is never silently
reported as completed and can be retried explicitly.

## Remaining production boundary

The v2 scheduler is a durable local orchestrator, not a distributed cluster
scheduler. Production deployment should later replace local JSON state with
SQLite/PostgreSQL, run workers as processes or containers, add leases and
heartbeats, and map remote bioinformatics jobs to Slurm job IDs.
