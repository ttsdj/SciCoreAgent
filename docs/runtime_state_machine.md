# BioCoreAgent Runtime 状态机与 DAG 调度

## Runtime 边界

Runtime 由三个持久化生命周期状态机和一个工具结果协议组成：

1. `TaskState` 管理一次 `ask()` 的多轮模型—工具循环。
2. `AgentJob` 管理一个 DAG 节点的依赖、重试、超时和终态。
3. `AgentTeam` 管理整个 DAG 的重规划、验证、合成和降级。
4. `ToolManager` 是所有模型可见工具的唯一执行入口。

状态仍以字符串写入 JSON，保证旧运行记录可读；运行时通过 Enum、状态集合和转移矩阵拒绝非法转移。

## 状态

### Task

```text
running -> completed
        -> stopped
        -> failed
```

每次多轮运行还持久化8个执行阶段：

```text
initializing
-> context_building
-> model_calling
-> output_parsing
-> tool_executing
-> context_building (下一轮)

output_parsing/tool_executing
-> recovering（按需）
-> finalizing
-> terminated
```

阶段变化写入 `task_phase_changed` Trace。模型调用抛出异常时，Runtime 会保存 `failed + terminated` 的 TaskState、`exception_raised` 和唯一 `run_finished`，然后继续向调用方抛出异常，避免把失败伪装成正常交付。

### Job

```text
queued -> waiting_dependencies -> running -> completed
   |               |                |
   +-> cancelled   +-> blocked      +-> queued (retry)
                                    +-> failed
                                    +-> cancelled
```

`created` 只作为审计事件的来源状态，不是持久化状态。终态 Job 不允许原地复活；显式 retry 会创建新 Job。

### Team

```text
queued -> running -> verifying -> synthesizing -> completed
              |                         +-------> degraded
              |                         +-------> failed
              +-> replanning -> running/verifying
              +-> synthesizing -> degraded (global timeout)
```

活动状态可以转入 `cancelled`。完整转移矩阵位于 `biocoreagent/lifecycle.py`。

## Tool Manager

工具执行统一经过：

```text
cancel gate
-> allowlist
-> registry lookup
-> schema/path validation
-> duplicate-call guard
-> risk approval
-> workspace snapshot
-> execution
-> result classification
-> memory/trace/evidence update
```

结果状态为 `ok`、`partial_success`、`error`、`rejected`。每次执行包含独立 `execution_id` 和 `duration_ms`。旧扩展仍可导入 `ToolExecutor`，它是 `ToolManager` 的兼容别名。

## DAG 拓扑并发

依赖名称和环在 Team 持久化前校验。每个 Job 等待上游 Job 的终态事件，不再通过固定间隔轮询。上游全部成功后进入共享 `asyncio.Semaphore`；任一上游失败、取消或阻塞时，下游进入 `blocked`。

线程模式使用 `asyncio.to_thread`，适合低成本或可协作取消的任务。需要硬超时和副作用隔离的任务应使用进程模式；Runtime 会终止超时进程树。

## 动态 Replan

当原始 Job 失败比例达到阈值，Runtime 调用 `replan_strategy`。策略返回 `ReplanPatch`，一个 patch 可以增加多个带依赖的新节点。

应用前必须通过：

- 节点名称非空、唯一且不与已有节点冲突。
- 角色属于已注册角色。
- 任务描述非空。
- 依赖节点存在。
- 新拓扑无自环和循环依赖。
- 节点超时不超过 Team 剩余预算。

接受或拒绝结果写入 Team 的 `replan_history`；拒绝原因同时写入审计 Trace。默认策略保持兼容：增加一个读取现有证据的恢复 Executor。

## 三级降级

1. 单 Job 超时或停滞：Job 进入 `failed`，`degradation_level=1`。
2. 批量失败达到阈值：Team 进入 `replanning`，应用 DAG patch，最终以 `degraded` 或 `failed` 交付。
3. Team 全局 deadline：取消未完成 Worker，保留已完成证据，强制合成部分结果，Team 进入 `degraded`。
