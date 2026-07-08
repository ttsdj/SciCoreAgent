# BiocoreagentV2.0

BiocoreagentV2.0 is a local, auditable research coding agent for bioinformatics-oriented work. It is built as a harness: the model proposes actions, while the runtime controls tools, workspace boundaries, approvals, traces, multi-agent jobs, and deterministic analysis routes.

## 3-Minute Interview View

### S - Situation

Bioinformatics coding tasks often mix fragile local environments, large data files, R/Python dependency conflicts, literature evidence, and long-running analysis scripts. A plain chat agent can easily loop on file reads, fabricate completion, or mutate an environment without enough auditability.

### T - Task

The project aims to turn a lightweight coding agent into a safer research agent that can:

- run inside any project directory;
- route common biological analysis tasks into governed workflows;
- keep secrets, raw data, and large artifacts out of Git;
- support local skills, wiki memory, PubMed/literature review, and code-literature provenance;
- use role-based multi-agent workers for exploration, planning, execution, and verification;
- degrade gracefully when heavy backends such as OmicVerse or DESeq2 are unavailable.

### A - Architecture

```text
CLI: biocoreagent-v2
  |
  +-- Runtime identity: BiocoreagentV2.0
  |
  +-- Agent harness
  |     +-- model client: DeepSeek / OpenAI-compatible / Anthropic-compatible / Ollama
  |     +-- tool executor: validation, approval, repeated-call guard, trace
  |     +-- workspace sandbox: all paths resolved under --cwd
  |     +-- final verifier: never claim success without verified artifacts
  |
  +-- Research workflow layer
  |     +-- analysis router: bulk RNA-seq / proteomics / single-cell / table / coding
  |     +-- transcriptome capabilities: OmicVerse check, DESeq2 fallback, plan artifacts
  |     +-- fallback script runner: one script, one run, classified errors
  |     +-- result exporter: deterministic CSV export without model tool loops
  |
  +-- Knowledge layer
  |     +-- .biocoreagent/wiki
  |     +-- .biocoreagent/skills
  |     +-- code-literature provenance links
  |     +-- PubMed and red-blue literature review tools
  |
  +-- Multi-agent scheduler
        +-- explorer / planner / executor / verifier / bio_worker roles
        +-- persistent jobs, teams, messages, retry, cancellation
```

### R - Result / Current Completion

Implemented:

- CLI entry point and project-local state under `.biocoreagent/`.
- Role-restricted multi-agent workers.
- Skill/wiki self-sedimentation and search/read tools.
- Literature tools, PubMed wrappers, red-blue review workflow, and XLSX export.
- Bulk RNA-seq routing with OmicVerse backend check and DESeq2 fallback.
- Controlled fallback for non-registered analysis types.
- CSV result export shortcut to avoid repeated `read_file/run_shell` loops.
- SSH tool skeleton with workspace policy checks.
- Safety tests and repository scan script.

Known limitations:

- OmicVerse is treated as an optional isolated backend, not a main dependency.
- Proteomics and single-cell are routed and fallback-controlled but not yet full deterministic backends.
- Some legacy compatibility modules remain internally, but the public project identity is BiocoreagentV2.0.

## Quick Start

### 1. Clone and install

```powershell
git clone <your-github-url> BiocoreagentV2.0
cd BiocoreagentV2.0
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### 2. Configure provider

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill only local values:

```env
BIOCOREAGENT_PROVIDER=deepseek
BIOCOREAGENT_DEEPSEEK_API_KEY=replace-me
BIOCOREAGENT_DEEPSEEK_API_BASE=https://api.deepseek.com/anthropic
BIOCOREAGENT_DEEPSEEK_MODEL=deepseek-chat
```

Never commit `.env`.

### 3. Run from any workspace

```powershell
biocoreagent-v2 --cwd D:\path\to\your\project --approval ask
```

Or from inside the workspace:

```powershell
cd D:\path\to\your\project
biocoreagent-v2 --approval ask
```

One-shot:

```powershell
biocoreagent-v2 --cwd D:\path\to\project "inspect counts.txt and plan el vs rest RNA-seq analysis"
```

## Optional OmicVerse Backend

Do not install OmicVerse into the main agent environment. Use an isolated conda environment:

```powershell
.\scripts\setup_omicverse_env.ps1 -EnvName biocore-omicverse
```

Then update `.env`:

```env
BIOCOREAGENT_OMICVERSE_ENABLED=1
BIOCOREAGENT_OMICVERSE_PYTHON=C:\path\to\conda\envs\biocore-omicverse\python.exe
```

The agent checks this backend before running OmicVerse-backed transcriptome steps. If it is missing, bulk RNA-seq falls back to deterministic DESeq2 or a controlled failure with repair instructions.

## Docker

Docker is for the lightweight agent runtime, not for bundled large biological datasets.

```powershell
docker compose build
docker compose run --rm biocoreagent-v2 --help
```

Mount a workspace:

```powershell
docker compose --env-file .env run --rm -v D:\path\to\project:/workspace biocoreagent-v2 --cwd /workspace --approval ask
```

## Safety Gates Before GitHub Push

Run:

```powershell
python scripts\check_repo_safety.py
python -m pytest tests\test_fused_runtime.py tests\test_cli_welcome.py -q
```

The safety script blocks common mistakes:

- committed `.env` or local state;
- real-looking API keys;
- large files;
- raw omics data extensions such as FASTQ/BAM/CRAM/H5AD/RDS;
- build artifacts and test caches.

## Repository Hygiene

Tracked code should include:

- `biocoreagent/`
- `pico/`
- `corecoder/`
- `mcp_servers/`
- `tests/`
- `scripts/`
- `README.md`
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `Dockerfile`
- `docker-compose.yml`

Do not commit:

- `.env`
- `.biocoreagent/`
- `.tmp/`, `.verify*/`, `.test-tmp*/`
- build outputs, wheels, egg-info
- real analysis data or result folders
- private tokens or user data

## Useful Commands

```powershell
biocoreagent-v2 --help
biocoreagent-v2 --cwd . --approval ask
biocoreagent-v2 --cwd . --max-steps 40 "summarize the repository architecture"
biocore-doctor
```

`biocoreagent` remains as a backward-compatible alias, but new documentation and deployment should use `biocoreagent-v2`.
