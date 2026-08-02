# BioCoreAgent 审计系统

## 一句话说明

BioCoreAgent 的审计系统不是只保存聊天记录，而是在每个 workspace 下保存一条可复盘的证据链：用户消息、工具调用、审批决策、状态转移、产物文件、错误和最终报告。

## 存储位置

普通会话审计：

```text
.biocoreagent/audit/sessions/<session_id>/
├── events.jsonl
├── messages.jsonl
├── tool_calls.jsonl
├── approvals.jsonl
├── state_transitions.jsonl
├── artifacts.jsonl
├── errors.jsonl
├── audit_index.json
└── final_report.md
```

多 agent 调度审计：

```text
.biocoreagent/audit/sessions/multiagent/
├── events.jsonl
├── messages.jsonl
├── state_transitions.jsonl
├── artifacts.jsonl
├── audit_index.json
└── final_report.md
```

底层 Pico 运行轨迹仍然保留在：

```text
.biocoreagent/runs/<run_id>/
├── task_state.json
├── trace.jsonl
└── report.json
```

审计系统会把这些运行产物注册到 `artifacts.jsonl`，并在 `audit_index.json` 中记录哈希。

## 事件类型

- `messages.jsonl`：用户、assistant、tool、supervisor 的消息摘要和内容哈希。
- `tool_calls.jsonl`：工具名、参数、结果摘要、风险等级、受影响文件、是否修改 workspace。
- `approvals.jsonl`：人工审批或策略审批，包括动作、参数、decision 和风险说明。
- `state_transitions.jsonl`：multi-agent job 的状态转移，例如 `queued -> running -> completed`。
- `artifacts.jsonl`：脚本、trace、report、worker result、team synthesis 等产物路径和 sha256。
- `errors.jsonl`：工具错误、拒绝、partial success、运行异常和恢复策略。
- `audit_index.json`：本次审计文件清单、事件计数和 sha256。
- `final_report.md`：给人看的审计摘要。

## 脱敏策略

写入审计前会统一脱敏：

- `api_key`
- `token`
- `password`
- `secret`
- `authorization`
- `bearer`
- `sk-...` 形态的 key

脱敏后的日志会保留结构，但不会保存明文密钥。

## 工程设计

审计层位于 `biocoreagent/audit.py`。

主 runtime 接入点：

```text
BioPico.record()
BioPico.emit_trace()
BioPico.execute_tool()
BioPico.approve()
BioPico.ask()
```

multi-agent 接入点：

```text
AsyncMultiAgentOrchestrator._transition()
AsyncMultiAgentOrchestrator._write_result_artifact()
AsyncMultiAgentOrchestrator._write_team_synthesis_artifact()
AsyncMultiAgentOrchestrator.send_message()
```

## 面试回答

我把审计系统设计成 workspace-local、append-only、JSONL-first 的证据链。Pico 原本的 run trace 负责记录单次执行细节，BioCoreAgent 的审计层负责把消息、工具、审批、状态、产物和错误统一归档到 session 级目录，并生成 `audit_index.json` 和 `final_report.md`。这样系统不仅能回答“最后结果是什么”，还能回答“谁做了什么、为什么允许做、产生了哪些文件、是否可验证”。
