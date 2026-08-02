# 三层记忆、压缩与评测

BioCoreAgent 的记忆路径为：SQLite 会话事实 → 本地工作记忆 → 可选 Postgres 蒸馏长期记忆。

```text
session history
  -> session_messages (SQLite)
  -> immutable conversation_chunks (SQLite, source URI + SHA-256)
  -> distillation_outbox (SQLite, retryable)
  -> background distillation worker (delivery does not wait for embeddings)
  -> Postgres long_term_memories + evidence (when configured)
  -> Postgres temporal research graph (entities/events/relations/evidence)
  -> Dense + exact BM25 + RRF
  -> relevant memory section in the prompt
```

## 本地可靠性

- `sessions.sqlite` 是 session、消息、chunk 与 outbox 的主存储；同目录 JSON 是人工可读镜像。
- 工作记忆仍在 session 中保存任务摘要、最近文件、文件摘要与过程笔记，且文件变化会使摘要失效。
- `.biocoreagent/memory/working.sqlite` 是独立的本地 User/Project 工作记忆；它把用户偏好和项目决策镜像为 `memory/user/*.md`、`memory/project/*.md`，每条笔记保留原消息 source URI 与 SHA-256。
- 未配置 Postgres 时，chunk 与 outbox 不丢弃；运行仍走本地 SQLite FTS5 + Dense Hash 记忆。

## 开启长期记忆

```powershell
python -m pip install -e ".[memory-postgres]"
$env:BIOCOREAGENT_MEMORY_POSTGRES_DSN="postgresql://user:password@localhost:5432/biocoreagent"
$env:BIOCOREAGENT_EMBEDDING_BACKEND="sentence-transformers"
$env:BIOCOREAGENT_EMBEDDING_MODEL="all-MiniLM-L6-v2"
```

本地开发可启动隔离数据库（默认 CLI 不会启动它）：

```powershell
docker compose --profile memory up -d memory-postgres
$env:BIOCOREAGENT_MEMORY_POSTGRES_DSN="postgresql://biocoreagent:biocoreagent_dev_only@127.0.0.1:54329/biocoreagent_memory"
python -m pytest tests/test_postgres_memory_integration.py -q
```

Postgres 保存蒸馏陈述、作用域、embedding、状态与 `long_term_memory_evidence`。每条结果都包含 `session://<id>/messages/<start>-<end>#sha256=<digest>`，可使用 `SessionStore.source_excerpt()` 回到原消息。默认规则蒸馏仅接受用户偏好、决策和稳定事实；其余 chunk 以 `rejected` 保留审计状态。

## 研究知识图谱

配置 Postgres 后，后台蒸馏 worker 会将同一条带证据的长期记忆投影到轻量级时态研究图谱：

- `research_entities`：用户、项目、方法/决策对象和代码/数据/报告产物。
- `research_events`：决策、观察、异常、恢复和偏好事件，分别保存 `valid_from`、`valid_to` 与数据库记录时间。
- `research_event_participants`：实体在事件中的 actor、context、object、artifact 等角色。
- `research_event_relations`：`caused_by`、`recovers`、`supersedes` 等事件关系。
- `research_evidence_links`：事件到原始 Session、Trace 或 Artifact URI 与 SHA-256 的证据关系。

默认规则投影只抽取可靠的作用域、文件路径和决策对象；高精度调用方可以在 memory candidate 的 `graph` 字段中显式提供事件类型、实体、有效时间和因果关系。图谱查询始终按显式 user/project scope 隔离，不把模型推断当作原始证据。

```powershell
biocoreagent --memory-timeline <user-scope> <project-scope>
biocoreagent --memory-event <event-id>
biocoreagent --memory-causal <event-id>
```

当前使用 PostgreSQL 关系表和递归 CTE 完成时间线与因果链遍历；在出现大规模多跳图查询需求前不引入 Neo4j。

`BIOCOREAGENT_MEMORY_USER_SCOPE` 是可选的用户/租户边界；同一 Postgres 实例必须为每个用户设置稳定且不可伪造的 scope 值。项目路径作为 project scope，二者都在召回前过滤。未提供 user/project scope 时只能读取显式全局行，不会退化成读取所有租户。

## 检索与压缩

长期记忆在 scope 过滤后执行 Dense 与精确 BM25，并以 RRF 融合；本地 SQLite 层继续提供 FTS5/BM25 + Dense Hash。现有上下文压缩保留四层：预算裁剪、重复读取消除、旧工具结构化摘要、全局阈值收缩。当前请求不裁剪。

## 指标边界

`evaluate_memory_recall()` 计算 HitRate@k、MRR@k 和 scope leakage rate。目标门槛为 HitRate@10 ≥ 99.4%、MRR@10 ≥ 0.67、scope leakage rate = 0。

当前仓库提供两个不同证据层级：

- `synthetic-v1`：200 条冻结的合成跨会话命名实体查询；真实 Postgres + `all-MiniLM-L6-v2` 实测 HitRate@10 100%、MRR@10 1.000、scope leakage 0，见 `artifacts/memory-recall-synthetic-v1.json`。它只证明工程链路达到门槛，不能描述为开放域语义 QA。
- `drafts/session_cases.jsonl`：由真实历史会话抽取的待人工标注草案。只有独立审阅者补齐未来问法、相关/禁止 memory id 并冻结后，才能形成真实跨会话效果声明。

冻结集采用 JSONL；每行至少有 `case_id`、`query`、`relevant_memory_ids`，并应带上 `user_scope`、`project_scope` 和跨租户的 `forbidden_memory_ids`。执行门槛：

```powershell
python scripts/evaluate_memory_recall.py `
  benchmarks/memory_recall/synthetic-v1/frozen.jsonl `
  --corpus benchmarks/memory_recall/synthetic-v1/corpus.jsonl `
  --output artifacts/memory-recall-synthetic-v1.json
```

命令默认以 HitRate@10 ≥ 0.994、MRR@10 ≥ 0.67、scope leakage rate = 0 判定通过；它会以非零退出码阻止不合格基线被误报为通过。

用本地会话生成待审核草案（不会覆盖已有文件）：

```powershell
python scripts/prepare_memory_recall_cases.py --sessions-root .biocoreagent/sessions --output benchmarks/memory_recall/drafts/session_cases.jsonl
```

草案的 `query` 为空，必须由审阅者填入独立的未来问法，并填写实际 `relevant_memory_ids` 后才能复制为冻结集。这样指标不会因“用原文检索原文”而失真。

审核时可只读查看单条草案关联的本地原消息：

```powershell
python scripts/review_memory_recall_drafts.py benchmarks/memory_recall/drafts/session_cases.jsonl --sessions-root .biocoreagent/sessions --case-id <draft_case_id>
```

旧 session 在升级前没有 outbox 时，可幂等回填到本地工作记忆和已配置的 Postgres：

```powershell
python scripts/backfill_memory_from_sessions.py --sessions-root .biocoreagent/sessions --workspace-root .
```
