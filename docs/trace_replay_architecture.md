# BioCoreAgent trace、代码溯源与回放

## 证据模型

一次可审计运行包含四类相互关联、但职责不同的证据：

1. `trace.jsonl`：Agent 的按序事件事实。
2. `source_manifest.jsonl` 和对象存储：当时实际使用或生成的代码内容。
3. `git_before.json`、`git_after.json`：仓库 commit、分支和未提交 patch。
4. `deliverables/`：产物与代码、环境、工具调用和 trace 的血缘关系。

`evidence_index.json` 为上述文件提供路径、大小和 SHA-256 清单。它用于完整性
检查，不等同于数字签名或不可抵赖证明。

代码对象存放在 `.biocoreagent/objects/sha256/`。文件路径后来被覆盖或删除后，
仍可使用 `object_id` 查看当时保存的脱敏内容。对象按哈希去重，不自动删除。

## 历史 trace 与 fresh replay

历史 trace 是证据，不自动成为正确答案。提取命令始终产生 `draft` case：

```powershell
biocore-replay case extract .biocoreagent\runs\<run_id> `
  --case-id example --output-root benchmarks\replay_cases
```

人工检查 fixture 和 verifier、解决所有 omission，并将
`requires_human_verifier_review` 设为 `false`、`status` 改为 `ready`。然后：

```powershell
biocore-replay case lint benchmarks\replay_cases\example
biocore-replay run benchmarks\replay_cases\example
```

Replay 在新的隔离目录中用当前 BioPico runtime 执行。reference trace 的工具
结果和最终答案不会进入模型上下文。首期禁止远程工具；`run_shell` 中的网络、
SSH 和下载命令也会被验证层拒绝。

## 查询交付物和代码

```powershell
biocore-replay trace validate .biocoreagent\runs\<run_id>
biocore-replay artifact explain result.csv --search-root .biocoreagent\runs
biocore-replay source show .biocoreagent\runs\<run_id> --at <event_id>
biocore-replay source materialize .biocoreagent\runs\<run_id> `
  --at <event_id> --target C:\tmp\restored-source
```

`source materialize` 只允许写入新的空目录，不覆盖当前项目。

## Scorecard

总分为 100：结果验证 50、产物与溯源 20、trace 完整性 15、异常恢复 10、
预算 5。所有硬门槛通过且总分至少 80 才算通过。

基线不会自动更新：

```powershell
biocore-replay compare scorecard.json --baseline baseline.json
biocore-replay baseline update scorecard.json --target baseline.json
```
