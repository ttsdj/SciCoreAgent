# BioCoreAgent Verified-50 评测与图表输出流程

本文档记录 BioCoreAgent 对 `phylobio/BixBench-Verified-50` 的评测流程，以及如何生成与 `bio-xyz/bio-benchmark` dashboard 同构的图表产物。

## 当前状态

- 数据集：`https://huggingface.co/datasets/phylobio/BixBench-Verified-50`
- 数据集类型：HuggingFace gated dataset，需要登录并接受条款。
- 本地目标目录：`F:\aicoding\bixbench_verified50`
- 当前阻塞：本机未检测到 HuggingFace token，无法下载 gated dataset。

## 一键流程

在项目根目录 `D:\aicoding\00.project\biocoreagent\V3` 运行：

```powershell
python scripts\run_verified50_benchmark.py
```

该脚本会依次执行：

1. 检查 HuggingFace token。
2. 下载 `phylobio/BixBench-Verified-50` 到 `F:\aicoding\bixbench_verified50`。
3. 使用 `corecoder.eval.bixbench` 跑 `BixBench-Verified-50.jsonl`。
4. 输出评测报告到 `F:\aicoding\bixbench_runs\verified50-deepseekchat-v1`。
5. 生成 bio-benchmark 风格图表到：
   `D:\aicoding\00.project\biocoreagent\V3\.biocoreagent\bixbench_runs\reports\bio_benchmark_verified50`

如果未登录 HuggingFace，脚本会返回结构化 blocker，不会继续误跑。

## 首次授权

如果出现 `huggingface_gated_dataset_auth_required`，先完成：

```powershell
hf auth login
```

然后打开数据集页面，接受访问条款：

```text
https://huggingface.co/datasets/phylobio/BixBench-Verified-50
```

授权完成后重新运行：

```powershell
python scripts\run_verified50_benchmark.py
```

## 手动分步命令

下载数据：

```powershell
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='phylobio/BixBench-Verified-50', repo_type='dataset', local_dir=r'F:\aicoding\bixbench_verified50')"
```

运行评测：

```powershell
python -m corecoder.eval.bixbench `
  --official-dir F:\aicoding\bixbench_verified50 `
  --official-jsonl BixBench-Verified-50.jsonl `
  --strategy biocoreagent_agent `
  --extract-capsules `
  --resume `
  --max-steps 20 `
  --task-timeout-seconds 600 `
  --output-dir F:\aicoding\bixbench_runs\verified50-deepseekchat-v1
```

生成图表：

```powershell
python scripts\build_bio_benchmark_chart.py `
  --report F:\aicoding\bixbench_runs\verified50-deepseekchat-v1\bixbench_report.json `
  --output-dir D:\aicoding\00.project\biocoreagent\V3\.biocoreagent\bixbench_runs\reports\bio_benchmark_verified50
```

## 图表产物

`scripts\build_bio_benchmark_chart.py` 会生成：

- `benchmark_summary.json`：类似 `bio-benchmark` 的汇总 JSON。
- `<run_id>.csv`：类似 `docs/data/results/*.csv` 的结果表。
- `bio_benchmark_chart.html`：本地可打开的 Direct pass@1 图表。

注意：BioCoreAgent 当前本地 runner 只计算 direct/pass@1，不计算 `MCQ with refusal` 或 `MCQ without refusal`。

## 验证命令

```powershell
python -m pytest tests\test_bixbench_eval.py -q --basetemp D:\aicoding\tmp\pytest-bixbench
```

当前通过标准：

- runner 能自动识别 `BixBench-Verified-50.jsonl`。
- 报告能标记 `benchmark.name = phylobio/BixBench-Verified-50`。
- 报告能标记 `verified_50.computed = true`。
- 图表转换脚本能从 BioCoreAgent 的 `bixbench_report.json` 生成 JSON、CSV 和 HTML。

## 当前非 Verified-50 参考结果

已有旧 50 题子集参考产物：

```text
D:\aicoding\00.project\biocoreagent\V3\.biocoreagent\bixbench_runs\reports\bio_benchmark_v16\bio_benchmark_chart.html
```

该结果来自 `F:\aicoding\bixbench_runs\official-agent-50-deepseekchat-v16`：

- pass@1：44/50 = 88%
- 注意：这不是 `phylobio/BixBench-Verified-50`，不能作为 Verified-50 最终成绩。
