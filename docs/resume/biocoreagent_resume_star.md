# BioCoreAgent 简历与面试证据稿

> 本文只使用当前代码和可复现产物能够证明的事实。所有指标均标注测试边界，避免把“文件存在”误写成“生产链路已启用”。

## 一句话介绍

BioCoreAgent 是一个科研导向的 Agent Harness：它在通用 ReAct 编码循环之外，增加确定性科学任务路由、多智能体 DAG 编排、可追溯记忆与知识沉淀、上下文压缩、安全审批和结果验证，使生物信息任务能够以“可执行、可恢复、可审计”的方式完成。

## 当前架构

```mermaid
flowchart LR
    U["用户任务"] --> R["Analysis Router<br/>5 类确定性路由"]
    R --> H["ReAct AgentLoop<br/>推理-工具-观察"]
    R --> C["Capability Registry<br/>已封装能力优先"]
    C --> F["Controlled Fallback<br/>一次脚本-执行-分类修复"]
    H --> T["67 个 Executor 工具<br/>29 个 Bio/Workflow 工具"]
    H --> M["Multi-Agent Supervisor"]
    M --> D["DAG + asyncio.Semaphore"]
    D --> W["Role Workers<br/>explorer/planner/executor/verifier/bio_worker"]
    H --> K["Memory / Skill / Wiki / RAG"]
    K --> S1["SQLite 会话态<br/>JSON 快照镜像"]
    K --> S2["本地 User/Project 工作记忆<br/>SQLite + Markdown"]
    K --> S3["Postgres 蒸馏长期记忆<br/>Dense + BM25 + RRF + 原文回跳"]
    K --> DR["DREAM 异步沉淀<br/>draft Skill + Wiki 证据"]
    H --> X["四层上下文压缩"]
    H --> G["Policy / Approval / Audit / Verifier"]
    W --> A["Artifact Registry + Completion Inbox"]
    H --> E["Canonical Trace + CAS 代码快照<br/>Replay + Scorecard"]
    A --> G
    G --> O["成功 / 降级成功 / 可诊断失败"]
```

当前 Harness 由 7 个可组合治理组件组成：

1. `AgentLoop`：ReAct 控制循环。
2. `analysis_router`：科学任务意图、风险和后端路由。
3. `domain/capability registry`：工具契约与专业能力注册。
4. `fallback_runner`：后端缺失时的一次性脚本执行器。
5. `analysis_verifier`：禁止“执行失败但声称完成”。
6. `orchestrator`：多 Agent DAG 调度、状态与降级。
7. `audit`：消息、工具、审批、状态、产物和错误审计。

其中 Skill 和 MCP 是扩展接口；上述 7 个组件是 Harness 内核，并非都宣称为第三方热插拔插件。

## 推荐简历表述

### 项目：BioCoreAgent 科研 Agent Harness

**背景（Situation）**

通用 Coding Agent 可以生成代码，但面对 RNA-seq、文献证据整理等科研任务时，容易出现方法路由不稳定、重复读文件、依赖错误后盲目重试、失败结果被误报为完成，以及跨会话知识无法复用的问题。

**任务（Task）**

我需要在轻量 Pico 执行内核上构建一个科研导向的 Agent Harness，使模型自由推理与确定性分析能力协同工作，并补齐多智能体调度、记忆、上下文治理、技能沉淀、安全边界、审计和 benchmark 评测。

**行动（Action）**

- 设计 ReAct Harness，AgentLoop 循环执行“意图推理 → 工具调用 → 观察反馈”，并增加分析路由、能力注册、受控 fallback、错误分类、自修复和最终结果 verifier；当前 Executor 注册 67 个工具，其中 29 个为生信或工作流治理工具，覆盖 bulk RNA-seq、蛋白组、单细胞、通用表格和普通 Coding 5 类确定性路由。
- 自研中心化多智能体编排器，使用 `asyncio` 事件循环、`Semaphore` 并发限流和 `asyncio.to_thread` 兼容同步 Worker；支持 DAG 依赖、隔离工作区、结构化消息、Artifact Registry 和 9 个核心运行态，另保留 `cancelled/blocked` 异常终态；实现三级降级：单任务超时分类、批量失败触发动态 replan、全局超时基于已完成证据强制合成。
- 构建三层记忆：SQLite 保存会话消息、不可变 chunk 和可重试蒸馏 outbox；本地 User/Project 工作记忆使用独立 SQLite 并镜像 Markdown；可选 Postgres 长期记忆保存蒸馏事实与证据，使用本地 SentenceTransformer Dense 向量、精确 BM25 和 RRF 混合召回，结果可通过 `session://...#sha256` 回跳原消息。未配置服务时自动回退到 SQLite FTS5/BM25 + Dense Hash。
- 实现四层上下文压缩：分区预算截断、重复读取裁剪、旧工具结果结构化精缩、全局阈值触发的自适应预算收缩；所有压缩行为写入 prompt metadata 和审计 trace。
- 构建 RAG + Skill + Wiki 双通道沉淀链路：显式请求同步保存；后台 DREAM 以 Detect/Review/Extract/Apply/Monitor 五阶段持久化异步执行，只采纳有工具证据的成功任务，累计 3 条同类观察后生成带 `draft` 标签的 Skill，继续积累后自动升级版本，并在覆盖前归档旧版本和生成 Wiki 证据记录。
- 构建本地可审计与回放评测层：Canonical Trace 记录完整脱敏输入、模型/工具事件、异常恢复、产物和唯一终态；CAS 保存交付时的精确代码内容，Git commit + dirty patch 保存项目现场；历史 Trace 只能抽取 draft replay case，ready case 由当前 Runtime 生成 fresh trace，并通过 100 分 verifier/scorecard 做基线回归。
- 完善中心化 Supervisor 的父子会话隔离与结果回注：每个 Worker 独立 session/run/执行日志/产物清单；终态结果写入按父会话隔离的 durable completion inbox，父 Agent 下一轮上下文一次性注入并保存消费游标。
- 建立工具治理边界：统一参数校验、工作区逃逸拦截、角色最小权限、高风险审批、重复调用拦截、敏感信息脱敏、partial success 识别、checkpoint、artifact verifier 和 JSONL/JSON 审计索引。

**结果（Result）**

- Harness 固定回归集 14/14 通过，任务通过率、预算内完成率、artifact verifier 通过率均为 100%。
- 真实 Postgres + `all-MiniLM-L6-v2` 在 200 条冻结合成跨会话资格集上 HitRate@10 100%、MRR@10 1.000、scope leakage 0，达到 99.4%/0.67 验收门槛；该指标只验证命名实体检索、排序和作用域链路，不代表开放域语义问答效果。
- 15 组长会话压测中，平均 Prompt 从 26,928 字符压缩到 1,795 字符，平均压缩率 92.95%，最高 95.23%；当前请求、最新证据保留率和预算合规率均为 100%。
- 8 Worker 调度压测中，`max_concurrency=4` 相比串行获得至少 2.0 倍端到端加速（3 次运行中位数，精确值保存在最新证据产物中）；该数字包含状态落盘、审计和 Artifact I/O 开销。
- 在官方 `phylobio/BixBench-Verified-50` 数据集上，BioCoreAgent 从初版 22/50（44%）提升到 38/50（76%），绝对提升 32 个百分点。该成绩使用本地 direct verifier，未宣称官方外部 LLM judge 分数。

## 可直接放入简历的精简版

**BioCoreAgent：科研导向 Agent Harness**

- 基于 Pico 内核设计 ReAct Harness，将模型自由工具循环与确定性科学任务路由结合，封装 7 个治理组件、5 类分析路由和 67 个 Executor 工具；通过 Capability Registry、受控脚本 fallback、错误分类自修复和最终结果 verifier 降低科研任务误报。
- 自研 `asyncio + Semaphore + to_thread` 多智能体 DAG 编排器，支持 5 类角色、隔离工作区、结构化消息、Artifact Registry、9 个核心运行态及三级降级；8 Worker 压测相对串行实现至少 2.0 倍端到端加速（3 次运行中位数）。
- 构建 SQLite 会话证据、本地 User/Project 工作记忆和 Postgres 蒸馏长期记忆三层体系，采用 SentenceTransformer Dense + BM25 + RRF 并保留 SHA-256 原文回跳；200 条冻结合成资格集 HitRate@10 100%、MRR@10 1.000、scope leakage 0。
- 实现预算截断、冗余裁剪、结构化精缩和自适应阈值裁剪四层上下文流水线；15 组长会话平均由 26,928 压至 1,795 字符，平均压缩率 92.95%，请求/最新证据保留率 100%。
- 构建 RAG + Skill + Wiki 双通道沉淀机制，支持显式唤起和五阶段 DREAM 持久化异步 Review；每 3 条成功同类观察生成或迭代 draft Skill，旧版本自动归档并关联 Wiki 证据。
- 构建 Canonical Trace、CAS 精确代码快照、Git dirty 现场、Deliverable Bundle 与 Fresh Replay/Verifier/Scorecard；Supervisor 通过父会话 completion inbox 自动回注子 Agent 结果。
- 建立参数校验、工作区隔离、最小权限、高风险审批、重复调用拦截、敏感信息脱敏、partial success 和审计链路；14 项固定 Harness 回归任务实现 100% 通过、100% 预算内完成和 100% verifier 通过。
- 在 BixBench Verified-50 上将 BioCoreAgent 初版 pass@1 从 44% 提升至 76%（+32pp，本地 direct verifier）。

## 不能写进简历的说法

以下表述当前没有证据，不能使用：

- “使用 pgvector ANN 检索”：当前 Postgres 实现将 embedding 保存为 JSONB，在作用域过滤后执行精确余弦；尚未使用 pgvector 索引。
- “真实用户跨会话 HitRate@10 100%”：当前 100%/1.000 来自 200 条冻结合成工程资格集；真实历史会话集仍处于待人工标注 draft 阶段。
- “多 Agent 可以硬终止任意 Python 线程”：当前单任务超时是协作式状态隔离，晚到结果会被丢弃；真正硬终止需要进程或容器 Worker。
- “BixBench 官方 judge 76%”：76% 是本地 direct verifier 的 Verified-50 成绩，官方外部 LLM judge 未运行。
- “长会话任务正确率 100%”：现有 100% 指标是请求保留、最新证据保留和预算合规，不是模型回答正确率。
- “原始模型从 44% 提升到 76%”：44% 是 BioCoreAgent 初版，不是未加 Harness 的纯 DeepSeek 基线。

## 面试追问

### Q：为什么多智能体不是纯 `asyncio`？

A：`asyncio` 负责 DAG 调度、依赖等待、超时、取消和 Semaphore 限流，但现有模型请求和 `agent.ask()` 是同步阻塞接口，因此 Worker 使用 `asyncio.to_thread` 执行。这样既保留异步调度能力，又不用一次性重写整个执行内核。如果后续把模型、SSH 和工具链全部异步化，可以逐步减少线程桥接。

### Q：为什么并发 4 只有约 2 倍，而不是接近 4 倍？

A：压测统计的是 3 次运行中位数的端到端耗时，包含线程调度、SQLite/JSON 状态落盘、审计日志、工作区与 Artifact 写入。测试 Worker 本身只有 250ms，固定治理开销占比较高，因此简历使用对多轮结果更稳健的“至少 2.0 倍”，精确值由证据脚本每次重算。长耗时模型或生信任务中，计算占比提高后并发收益通常会更明显，但需要另做生产负载测试。

### Q：为什么 Postgres 没有直接使用 pgvector？

A：首期先用 stock PostgreSQL 保存蒸馏记忆、作用域和证据，在过滤后的个人/项目小规模候选集上计算精确 BM25 与余弦，优先验证三层数据契约、跨会话回跳和租户隔离。规模扩大后可以把候选获取替换为 pgvector ANN 或专用 BM25 扩展，而不改变 evidence、verifier 和 scorecard 语义。

### Q：如何避免错误经验沉淀为 Skill？

A：后台 Reviewer 不从失败、Recovery 或无工具证据的任务学习；同类流程至少成功出现 3 次才生成 Skill，并强制标记为 `draft`。每次更新前归档旧版本，Wiki 记录观察次数和 Skill 路径，用户可以回看证据或回滚。这个设计降低错误沉淀风险，但不能替代人工审查。

### Q：三级降级分别解决什么问题？

A：一级处理单 Worker 超时，将其分类并阻止晚到结果覆盖状态；二级在原始任务批量失败比例达到阈值时创建一次恢复 Job，基于已有证据动态 replan；三级在团队全局预算耗尽时停止未完成工作，对已完成 Artifact 强制合成，并把最终状态标为 `degraded`，禁止伪装成完整成功。

## 复现命令

```powershell
cd D:\aicoding\00.project\biocoreagent\V3

python -m pytest -q --basetemp=D:\aicoding\tmp\pytest-biocore-final

python -c "from pico.evaluation.evaluator import run_harness_regression_v2; import json; r=run_harness_regression_v2(); print(json.dumps(r['summary'], indent=2))"

python scripts\benchmark_resume_metrics.py

$env:BIOCOREAGENT_MEMORY_POSTGRES_DSN="postgresql://biocoreagent:biocoreagent_dev_only@127.0.0.1:54329/biocoreagent_memory"
$env:BIOCOREAGENT_EMBEDDING_BACKEND="sentence-transformers"
python scripts\evaluate_memory_recall.py benchmarks\memory_recall\synthetic-v1\frozen.jsonl --corpus benchmarks\memory_recall\synthetic-v1\corpus.jsonl --output artifacts\memory-recall-synthetic-v1.json
```

## 证据索引

- `artifacts/harness-regression-v2.json`
- `artifacts/resume-metrics-v1.json`
- `artifacts/memory-recall-synthetic-v1.json`
- `docs/trace_replay_architecture.md`
- `docs/knowledge_sedimentation.md`
- `docs/metrics/biocoreagent-resume-evidence.md`
- `tests/test_memory_context_metrics.py`
- `tests/test_multiagent_orchestrator.py`
- `F:/aicoding/bixbench_runs/verified50-deepseekchat-v1/bixbench_report.json`
- `F:/aicoding/bixbench_runs/verified50-deepseekchat-v10-full/bixbench_report.json`
