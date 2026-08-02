# RAG + Skill + Wiki 与 DREAM 异步沉淀

BioCoreAgent 提供两条知识沉淀通道：

1. 人工显式触发：用户明确要求记住内容、保存 Wiki 或保存 Skill 时，当前回合同步落盘并返回产物。
2. DREAM 后台通道：成功且有工具证据的回合被持久化排队，后台线程执行 Detect → Review → Extract → Apply → Monitor，不阻塞最终回答。

## DREAM 证据

每个后台任务保存于：

```text
.biocoreagent/sedimentation/dream/jobs/<dream_id>.json
```

任务记录五个阶段、当前状态、结果、错误和更新时间。干净关闭时 Runtime 在限定时间内等待队列；重启时，`queued/running` 任务会重新入队。失败与未验证回合标记为 `rejected`，不会生成观察或 Skill。

默认 Reviewer 采用保守门槛：

- 必须存在工具调用证据。
- 工具状态不能是 `error/rejected`。
- 最终回答不能包含失败或 Recovery 标记。
- 同主题至少积累 3 条成功观察后才生成 `draft` Skill。
- 后续每 3 条观察升级一次版本；覆盖前自动归档旧版。
- 每次创建或升级同时生成 Wiki 证据条目。

自动生成的 Skill 始终带 `draft`，它代表“可供人工审查的候选经验”，不代表已批准的生产流程。

## 与记忆流水线的关系

DREAM 管理可执行技能经验；会话记忆流水线管理事实、偏好和项目决策。两者都异步，但证据载体不同：

```text
成功工作流 -> DREAM -> versioned draft Skill + Wiki evidence
会话消息   -> immutable chunks -> distillation outbox
           -> local User/Project memory
           -> optional Postgres long-term memory
```

两条链路均保留 source session / source URI 和 SHA-256，不从失败回合学习，也不自动删除历史版本或执行 GC。
