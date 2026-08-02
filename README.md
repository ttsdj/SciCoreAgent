# SciCoreAgent

面向复杂科研研究任务的多智能体协作与可审计执行系统。

> 项目状态：科研工程原型。仓库已经实现并测试了多智能体编排、证据追踪、回放评测、上下文治理和三层记忆等核心链路；它仍需要真实用户数据验证、生产级安全加固和长期运行观测，不应被描述为“已经替代科研人员的全自动科学家”。

仓库名称为 **SciCoreAgent**。为保持已有安装和脚本兼容，当前 Python 包名及命令仍使用 **BiocoreagentV2.0 / biocoreagent-v2**；后续如更名会提供迁移期，不会静默破坏旧接口。

## 为什么做这个项目

科研 Agent 的难点不只是生成代码。复杂研究任务通常涉及脆弱的 Python/R 环境、大文件、长时间运行脚本、文献证据、多阶段依赖和失败恢复。如果只有一个自由工具循环，很容易发生重复读取、盲目重试、未验证却声称完成，或无法回答“这个结果由当时哪一版代码生成”。

SciCoreAgent 在模型与工具之间加入可执行治理层，使任务具备以下性质：

- **可编排**：Supervisor 将长任务拆成 DAG，由角色化子 Agent 并发执行。
- **可恢复**：状态机、checkpoint、动态 replan 和三级降级保留有效进展。
- **可审计**：Trace、代码快照、Git 现场、环境与产物血缘形成证据链。
- **可回放**：历史运行可抽取 replay case，由当前 runtime 生成 fresh trace 并评分。
- **可沉淀**：RAG、Skill、Wiki 和 DREAM 后台审查积累有证据的成功经验。
- **可控记忆**：会话态、工作记忆和长期记忆分层保存，可检索并回跳原文。
- **科研导向**：确定性分析路由、能力注册、受控 fallback 和结果 verifier 降低误报。

## 系统架构

~~~mermaid
flowchart TD
    U["用户任务"] --> CLI["CLI / Session Runtime"]
    CLI --> AR["科研任务路由与 Capability Registry"]
    CLI --> AL["ReAct AgentLoop"]
    AL --> TM["Tool Manager<br/>Schema · Policy · Approval · Workspace"]
    AL --> SUP["中心化 Supervisor"]
    SUP --> DAG["DAG Scheduler<br/>asyncio + Semaphore"]
    DAG --> W["Role Workers<br/>explorer · planner · executor · verifier · bio_worker"]
    W --> CI["Completion Inbox<br/>结果回注主会话"]

    AL --> CM["四层上下文压缩"]
    AL --> MEM["三层记忆"]
    MEM --> S1["SQLite 会话态"]
    MEM --> S2["本地 User / Project 工作记忆"]
    MEM --> S3["Postgres 蒸馏长期记忆<br/>Dense + BM25 + RRF"]

    AL --> KS["RAG + Skill + Wiki"]
    KS --> DR["DREAM 异步审查与版本迭代"]

    TM --> ES["Canonical Event Sink"]
    W --> ES
    ES --> TR["Trace + Evidence Index"]
    TM --> CAS["CAS 精确代码快照"]
    TM --> ART["Artifact Registry<br/>Deliverable Bundle"]
    TR --> RP["Replay Case"]
    RP --> FR["Current Runtime Fresh Run"]
    FR --> VF["Verifier + Scorecard"]
~~~

### 多智能体编排

- 中心化 Supervisor 管理父子会话隔离、异步执行、状态查询、日志、产物列表与结果回注。
- DAG 调度器使用 asyncio、Semaphore 和同步 Worker 线程桥接；依赖满足的节点并发执行。
- 9 个核心运行态描述正常生命周期，同时保留 cancelled 和 blocked 异常终态。
- 三级降级分别处理单 Worker 超时、批量失败触发动态 replan、全局预算耗尽后的证据合成。
- 线程 Worker 采用协作式超时隔离；需要硬终止时可使用进程 Worker。系统不声称能够强杀任意 Python 线程。

详细设计见 [多智能体设计](docs/multiagent_design.md) 和 [运行时状态机](docs/runtime_state_machine.md)。

### 评测、证据与回放

一次运行的核心证据链为：

~~~text
交付物
  → 精确生成代码快照（SHA-256 内容寻址对象）
  → 输入文件哈希与参数
  → 执行命令、工作目录和退出状态
  → Python / R / 系统环境
  → Trace 事件区间
  → Git commit + dirty patch
~~~

Canonical Trace 记录脱敏后的用户输入、模型/工具事件、文件影响、审批、异常恢复、产物和唯一终态。重要产物通过 Deliverable Bundle 绑定 lineage、environment、code manifest 与 verifier 结果。历史 trace 只能抽取 draft case；fixture 和 verifier 明确后才能作为 ready case重新驱动当前 runtime。

详细设计见 [审计系统](docs/audit_system.md) 和 [Trace / Replay 架构](docs/trace_replay_architecture.md)。

### 上下文压缩与记忆

上下文治理依次执行预算截断、冗余读取裁剪、旧工具结果结构化精缩、全局阈值自适应裁剪，并将压缩行为写入 prompt metadata 和 trace。

三层记忆分别承担：

1. SQLite 会话态：消息、不可变 chunk、蒸馏 outbox 与 JSON 人类可读镜像。
2. 本地 User / Project 工作记忆：独立 SQLite 存储，并镜像 Markdown。
3. 可选 Postgres 长期记忆：保存蒸馏事实、作用域和证据；使用 SentenceTransformer Dense、BM25 与 RRF 混合召回，并通过 session://...#sha256 回跳原消息。

未配置 Postgres 时，系统回退到本地 SQLite FTS5/BM25 + Dense Hash。当前 Postgres embedding 保存为 JSONB，在作用域过滤后的候选集上计算精确余弦；**尚未使用 pgvector ANN 索引**。

详细设计见 [记忆架构](docs/memory_architecture.md)。

### 知识与技能沉淀

- 用户显式请求可同步保存 Skill / Wiki。
- DREAM 后台流程按 Detect、Review、Extract、Apply、Monitor 五阶段持久化执行。
- 只有存在工具证据的成功任务才参与学习；同类观察累计达到阈值后生成带 draft 标记的 Skill。
- 更新前归档旧版本，并在 Wiki 中保留来源证据。自动沉淀用于形成候选知识，不能替代人工科学审查。

详细设计见 [知识沉淀](docs/knowledge_sedimentation.md)。

## 已验证结果与边界

下表是仓库当前保存的工程资格测试结果，不是未经限定的生产效果宣传。

| 项目 | 结果 | 测试边界与证据 |
|---|---:|---|
| 当前全量测试 | 280 passed，10 skipped | 2026-08-02，Python 3.13.13；跳过项为当前环境未启用的条件性集成测试；命令见“评测与测试” |
| 固定 Harness 回归 | 14/14 通过；预算合规与 artifact verifier 均为 100% | FakeModelClient 确定性任务集；[原始 JSON](artifacts/harness-regression-v2.json) |
| 长上下文压缩 | 15 组平均 26,928 → 1,795 字符，平均 92.95%，最高 95.23% | 当前请求、最新证据保留率及预算合规率均为 100%；不是模型答案正确率；[证据](artifacts/resume-metrics-v1.json) |
| 多 Agent 调度 | 8 Worker、并发 4 相对串行约 2.40× 端到端加速 | 250 ms 合成 Worker，包含状态、审计和 Artifact I/O；不能外推为真实模型任务固定加速比；[证据](artifacts/resume-metrics-v1.json) |
| 长期记忆召回 | HitRate@10 100%，MRR@10 1.000，scope leakage 0 | 真实 Postgres + all-MiniLM-L6-v2 上的 200 条冻结合成命名实体资格集；阈值为 99.4% / 0.67；不代表真实用户或开放域问答；[原始 JSON](artifacts/memory-recall-synthetic-v1.json) |
| Research Graph | 8 个冻结策划场景，资格分 100/100 | 仅验证策划工程场景，不代表开放域抽取效果；[原始 JSON](artifacts/research-graph-curated-v1.json) |
| BixBench Verified-50 | 初版 22/50（44%）→ 最佳 38/50（76%），+32pp | 使用本地 direct verifier；未运行官方外部 LLM judge。大型原始报告保存在仓库外；[工作流与边界](docs/verified50_benchmark_workflow.md) |

完整口径、复现命令和禁止使用的夸大表述见 [工程证据说明](docs/metrics/biocoreagent-resume-evidence.md) 与 [目标完成审计](docs/resume/goal_completion_audit.md)。

## 快速开始

### 环境要求

- Python 3.10+
- Windows PowerShell 或兼容 Shell
- 至少一个模型后端：DeepSeek、OpenAI-compatible、Anthropic-compatible 或 Ollama
- Docker（仅在需要本地 Postgres 记忆服务时使用）

### 安装

~~~powershell
git clone https://github.com/ttsdj/SciCoreAgent.git
cd SciCoreAgent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
~~~

### 配置模型

~~~powershell
Copy-Item .env.example .env
notepad .env
~~~

密钥只写入本机 .env；该文件已被 Git 忽略。示例：

~~~env
BIOCOREAGENT_PROVIDER=deepseek
BIOCOREAGENT_DEEPSEEK_API_KEY=replace-me
BIOCOREAGENT_DEEPSEEK_API_BASE=https://api.deepseek.com/anthropic
BIOCOREAGENT_DEEPSEEK_MODEL=deepseek-chat
~~~

也可通过 --provider 选择 ollama、openai 或 anthropic。请根据对应服务填写模型名与 base URL。

### 运行任务

交互模式：

~~~powershell
biocoreagent-v2 --cwd D:\path\to\project --approval ask
~~~

一次性科研任务：

~~~powershell
biocoreagent-v2 --cwd D:\path\to\project --approval ask "检查 counts.tsv，并制定可验证的差异分析计划"
~~~

查看完整参数：

~~~powershell
biocoreagent-v2 --help
~~~

默认审批策略为 ask。auto 会减少交互但不会取消策略校验；never 会拒绝需要人工批准的高风险动作。

## 可选 Postgres 长期记忆

安装可选依赖并启动仅绑定本机的开发数据库：

~~~powershell
python -m pip install -e ".[memory-postgres]"
docker compose --profile memory up -d memory-postgres
~~~

在本机 .env 中配置：

~~~env
BIOCOREAGENT_MEMORY_POSTGRES_DSN=postgresql://biocoreagent:biocoreagent_dev_only@127.0.0.1:54329/biocoreagent_memory
BIOCOREAGENT_MEMORY_USER_SCOPE=local-user
BIOCOREAGENT_EMBEDDING_BACKEND=sentence-transformers
BIOCOREAGENT_EMBEDDING_MODEL=all-MiniLM-L6-v2
~~~

compose 文件中的密码只用于本机开发。生产环境必须使用外部密钥、访问控制、备份与迁移方案。

## 审计与回放示例

解释一个交付物：

~~~powershell
biocore-replay artifact explain path\to\artifact.csv
~~~

查看运行在某事件时捕获的源代码：

~~~powershell
biocore-replay source show .biocoreagent\runs\RUN_ID --at EVENT_ID
~~~

将当时代码重建到新的空目录（不会覆盖当前项目）：

~~~powershell
biocore-replay source materialize .biocoreagent\runs\RUN_ID --at EVENT_ID --target D:\empty\reconstructed
~~~

从历史运行抽取 replay case，并使用当前 runtime 生成 fresh trace：

~~~powershell
biocore-replay case extract .biocoreagent\runs\RUN_ID --case-id my-case
biocore-replay run benchmarks\replay_cases\my-case\case.json
~~~

查看全部子命令：

~~~powershell
biocore-replay --help
~~~

## 评测与测试

发布前安全检查：

~~~powershell
python scripts\check_repo_safety.py
~~~

全量测试：

~~~powershell
python -m pytest -q --basetemp C:\tmp\pytest-scicoreagent
~~~

固定 Harness 回归、上下文压缩和调度指标：

~~~powershell
python -c "from pico.evaluation.evaluator import run_harness_regression_v2; import json; print(json.dumps(run_harness_regression_v2()['summary'], indent=2))"
python scripts\benchmark_resume_metrics.py
~~~

内置 BixBench-compatible smoke（不等同于官方完整数据集）：

~~~powershell
python -m corecoder.eval.bixbench --output-dir .biocoreagent\bixbench_runs\smoke
~~~

大型 benchmark 数据、原始生物数据和运行输出应放在仓库外，不应提交到 Git。

## 目录结构

~~~text
biocoreagent/       统一 runtime、多 Agent Supervisor、审计、证据和 replay
pico/               轻量 AgentLoop、上下文、会话态、记忆与评测内核
corecoder/          科研工具、能力路由、Skill/Wiki 沉淀及 benchmark adapter
benchmarks/         固定工程资格集、fixture 与 replay case
tests/              单元、集成、回放及确定性回归测试
artifacts/          可公开复核的小型指标证据
docs/               架构、边界、复现说明与设计记录
scripts/            安全检查、benchmark 和记忆评测脚本
~~~

运行态默认写入 .biocoreagent/ 或 .pico/，两者都被 Git 忽略。

## 安全与数据治理

- .env、数据库、日志、缓存、原始测序数据和常见大型生物格式默认忽略。
- 工具路径解析受 --cwd 工作区约束，高风险调用遵循审批策略。
- Trace 入库前执行敏感信息脱敏；大型输入默认保存路径和哈希，而非复制数据。
- CAS 通过 SHA-256 去重并保留精确代码版本；首期提供完整性验证，不宣称数字签名级不可抵赖。
- Replay 默认面向隔离 fixture；不要把生产密钥或患者数据放入 case。
- 在受监管或临床场景使用前，必须另行完成权限、隐私、合规和科学验证。

运行 [仓库安全检查](scripts/check_repo_safety.py) 可发现疑似密钥、大文件和不应提交的运行态路径。

## 当前限制

- 尚未完成真实用户跨会话记忆数据集的人工标注；目前公开结果来自冻结合成资格集。
- Postgres 检索没有 pgvector ANN，在大规模候选集上的性能尚未验证。
- 真实模型回放受模型漂移、网络和费用影响；提交级回归主要使用确定性 FakeModel。
- 第三方科研后端不可用时会降级或诊断失败；系统不会把降级结果伪装成完整成功。
- 自动生成的 Skill 仍需人工审查，不能直接视为科学事实。
- 当前以 Windows 本地开发验证为主，Linux、容器化和长时间生产运行仍需扩大测试覆盖。

## License

[MIT License](LICENSE)
