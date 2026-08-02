# BioCoreAgent Multi-Agent Harness 面试介绍

## 一句话说明

BioCoreAgent 的 multi-agent harness 不是让多个模型自由聊天，而是用中心化 Supervisor 管理任务状态、角色权限、并发执行、产物注册和最终验证，让科研 coding 任务可以被拆分、审计、恢复和验收。

## 架构层

我们采用的是 **Central Supervisor + Role-restricted Workers + Durable State + Artifact Registry** 架构。

核心链路：

```text
User Task
  -> Supervisor / Orchestrator
  -> Team DAG / Job Queue
  -> Role Worker: explorer / planner / executor / verifier / bio_worker
  -> Isolated Workspace
  -> Artifact Registry
  -> Team Synthesis
  -> Final Verification
```

为什么没有直接采用 AutoGen/CrewAI 群聊式架构：

- 生信和代码任务的核心不是“多智能体讨论”，而是“可控执行”。
- 我们需要明确权限边界，例如 explorer 只读、planner 只规划、verifier 只验证。
- 生信任务必须保留输入、参数、结果、错误和 provenance，不能只保留一段自然语言对话。
- 中心化 Supervisor 更容易做审批、取消、重试、DAG 依赖、状态恢复和最终一致性检查。

当前实现：

- `AsyncMultiAgentOrchestrator` 负责中心调度。
- `AgentJob` 表示单个 worker 任务。
- `AgentTeam` 表示一组 role worker 的 DAG。
- `AgentTransition` 记录状态转移审计轨迹。
- `AgentArtifact` 记录 worker result 和 team synthesis 等产物。
- `JsonStateStore` 用 JSON/JSONL 持久化 job、team、message、transition、artifact。

## 工程层

工程上我重点解决了四个问题：

1. **角色边界**

   BioCoreAgent 定义了 `explorer / planner / executor / verifier / bio_worker`。不同角色拿到不同工具集合，避免只读探索 agent 意外写文件，也避免 verifier 修改被验证对象。

2. **任务隔离**

   每个 worker job 会获得独立工作目录：

   ```text
   .biocoreagent/multiagent/workspaces/<job_id>/
   ```

   worker 的 session、run store 和 result artifact 都写到自己的工作区，避免多个 agent 并发污染同一上下文。

3. **可恢复状态**

   job/team 状态持久化到：

   ```text
   .biocoreagent/multiagent/jobs/
   .biocoreagent/multiagent/teams/
   .biocoreagent/multiagent/transitions/
   .biocoreagent/multiagent/artifacts/
   ```

   如果 orchestrator 重启，正在 running 的 job 会被标记为 failed，并提示需要显式 retry，避免“假装还在跑”。

4. **产物注册**

   worker 完成后会生成 `result.md`，team 完成后会生成 `synthesis.md`，并写入 artifact registry。最终回答可以引用真实产物，而不是只依赖模型记忆。

已暴露工具：

- `agent_start`
- `agent_status`
- `agent_cancel`
- `agent_retry`
- `agent_team_start`
- `agent_team_status`
- `agent_team_cancel`
- `agent_message`
- `agent_artifacts`

## 性能层

性能设计重点不是追求极限吞吐，而是让长任务并发、可控、可取消。

关键点：

- 使用独立 asyncio event loop + background thread 管理调度。
- 使用 semaphore 控制最大并发数，默认通过 CLI 的 `--max-agents` 配置。
- worker 执行放到 thread 中，避免阻塞 orchestrator loop。
- team 支持 DAG 依赖：无依赖任务并发执行，有依赖任务等待上游完成。
- 状态查询是读取本地 JSON 文件，成本低，适合 CLI 高频轮询。
- 每个 worker 的输出截断/产物化，避免把所有上下文塞回主 agent。

性能收益：

- 探索、规划、验证等互相独立的任务可以并发运行。
- 后台 worker 可以执行耗时检查，主 agent 保持响应。
- 失败任务可以单独 retry，不必重跑整个 team。
- 状态和产物持久化后，可以做断点恢复和审计复盘。

## 面试高频问题回答

### 1. 这算不算真正的多 agent？

算，但不是群聊式 multi-agent，而是工程化的中心编排式 multi-agent。

我们的 agent 之间不是自由对话，而是由 Supervisor 管理任务队列、角色权限、DAG 依赖、状态持久化和产物合成。这个形态更适合 coding agent 和生信分析，因为它强调可控、可审计、可恢复。

### 2. 为什么不用 AutoGen 或 CrewAI？

AutoGen 和 CrewAI 更适合快速搭建角色协作 demo 或开放式讨论，但 BioCoreAgent 的核心需求是安全执行和科研可复现。我们已经有 Pico runtime、工具审批、session、run store、domain tools 和 recovery 机制，所以直接接外部框架会引入重复抽象。

我选择保留现有 runtime，在其上实现中心化 orchestrator，这样可以复用已有安全边界，并把多 agent 能力和项目工具链深度整合。

### 3. 最大工程挑战是什么？

最大挑战是避免多 agent 变成“多个模型一起不可靠”。所以我没有把重点放在 agent 互聊，而是先做：

- 角色工具边界
- 状态持久化
- 产物注册
- 工作区隔离
- DAG 依赖
- 失败重试和取消

这些机制保证 agent 可以并发，但每一步都能追踪、审计和恢复。

### 4. 和普通线程池有什么区别？

线程池只能并发执行函数；multi-agent harness 管的是任务生命周期。

它不仅有并发，还有：

- role policy
- session/run isolation
- durable job/team state
- message bus
- dependency graph
- artifact registry
- synthesis and verification boundary

所以线程池只是底层执行手段，harness 才是上层工程抽象。

### 5. 后续还能怎么升级？

下一步可以升级为：

- Git worktree 级别的代码修改隔离。
- 更严格的 typed state graph。
- Team plan approval gate。
- Red-Blue reviewer 作为 verifier 前置节点。
- Artifact schema，例如 result table、log、plot、report 分类型注册。
- Agent scoring，根据历史成功率自动选择 worker role 或工具路径。
