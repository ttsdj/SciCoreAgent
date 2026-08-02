# SciCoreAgent 简历目标验收清单

> 审计日期：2026-07-30
> 口径：只有代码、自动化测试或可复现评测产物能够证明的能力才标记为完成。

## 当前结论

| 简历目标 | 状态 | 主要证据或缺口 |
|---|---|---|
| 多轮 Runtime、Tool Manager、9 状态生命周期 | 已完成 | `pico/agent_loop.py`、`pico/tool_executor.py`、`biocoreagent/lifecycle.py` |
| asyncio + Semaphore 的 DAG 依赖并发 | 已完成 | `biocoreagent/orchestrator.py`、多智能体专项测试 15/15 |
| 动态 Replan 与三级降级 | 已完成 | 单任务超时、失败子图重规划、全局超时强制合成均有自动化测试 |
| Supervisor、父子隔离、异步状态/日志/产物、结果回注 | 已完成 | durable completion inbox 与 recipient scope 测试 |
| Canonical Trace、异常恢复、文件产物与最终交付证据 | 已完成 | `biocoreagent/evidence.py`、`tests/test_replay_evidence.py` |
| Historical Trace → Draft Case → Fresh Replay | 已完成 | `biocoreagent/replay.py`、ready/draft 硬门槛测试 |
| Verifier、Scorecard、Baseline Diff | 已完成 | Replay smoke 100/100，安全硬门槛通过 |
| RAG + Skill Registry + Wiki | 已完成 | 统一知识库、版本化 Skill 文件和 Wiki 证据 |
| DREAM 后台异步沉淀与 Skill 新增/修补/版本归档 | 已完成 | durable DREAM queue、恢复与版本归档测试 |
| Tool → Skill → Skill Catalog 二阶段路由 | 本轮补齐 | 有界 Catalog 候选召回、元数据精排、边界过滤及诊断信息 |
| 四层上下文压缩 | 已完成 | 15 组长会话评测平均压缩率 92.95% |
| SQLite + Local Working Memory + Postgres 长期记忆 | 已完成 | SQLite/Markdown 镜像、outbox、真实 Postgres 集成测试 |
| Dense + BM25 混合检索、来源定位、原文回跳 | 已完成 | RRF 检索和 `session://...#sha256` 来源接口 |
| 实体、事件、有效时间和证据关系知识图谱 | 本轮补齐 V1 | PostgreSQL 时态图谱、异步双写、时间线/解释/因果链查询 |
| 知识图谱质量评测与安全硬门槛 | 已完成 | 8 个冻结精选科研场景，Scorecard 100/100 |
| 真实用户跨会话记忆指标 | 未完成 | 目前只有 200 条冻结合成工程资格集；真实会话草案仍需独立人工标注 |
| BixBench 官方外部 LLM Judge | 未完成 | 当前 44%→76% 使用本地 direct verifier |

## 本轮新增验收

- 新增 PostgreSQL `research_entities`、`research_events`、`research_event_participants`、`research_event_relations` 与 `research_evidence_links`。
- 长期记忆 outbox 在后台处理时同时写入向量索引与研究图谱。
- 支持事件有效时间、原始证据回跳以及 `caused_by`、`recovers`、`supersedes` 递归链查询。
- 新增 `--memory-timeline`、`--memory-event`、`--memory-causal` 查询入口。
- Skill Router 从全量单阶段触发评分升级为 Catalog 候选召回、元数据精排和适用边界过滤。
- 新增知识图谱/路由单元测试，并通过真实 PostgreSQL 端到端测试。

## 指标表述校正

- BixBench 证据是 BioCoreAgent 初版 22/50（44%）到最佳版 38/50（76%），即绝对提升 **32 个百分点**，不是“基模提升 20%”；且必须注明本地 direct verifier。
- 上下文证据是 15 组长会话平均 **92.95%**，不是 91.42%。
- 记忆实测为冻结合成资格集 HitRate@10 **100%**、MRR@10 **1.000**、scope leakage 0；99.4%/0.67 是验收门槛。若简历使用更保守数字，应写成“达到 ≥99.4%/≥0.67 验收门槛”，不能暗示真实用户集实测。

## 后续必须完成

- 从真实历史会话抽取并由独立审阅者标注跨会话查询、相关记忆和禁止记忆，冻结后重新计算 HitRate/MRR。
- 知识图谱精选工程资格集已覆盖实体、时间、关系和证据评测；下一阶段仍需补充自然产生的真实科研会话样本。
- 如需宣称 BixBench 官方成绩，接入官方外部 Judge；否则长期保留“本地 direct verifier”边界。
- 知识图谱 V1 是关系型轻量图谱；只有出现大规模多跳需求后才评估 Neo4j/GraphRAG。
