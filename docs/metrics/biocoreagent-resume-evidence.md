# BioCoreAgent Resume Evidence

- Generated at: `2026-07-24T14:10:46+00:00`
- Git commit: `5b6921b641ace0cac98c0077ac903d6334ea128f`

## Verified Metrics

- Harness regression: 14/14 passed (100.0%); budget compliance 100.0%; verifier pass 100.0%.
- Hybrid memory controlled recall: HitRate@10 100.0%, MRR@10 1.000 over 40 queries.
- Context compression: 15 long-session cases, average 26928 -> 1795 chars, average compression 93.0%, maximum 95.2%; current request retention 100.0%, latest evidence retention 100.0%, budget compliance 100.0%.
- Multi-agent scheduler: 8 workers, concurrency 1 -> 4, 2.481s -> 1.033s, 2.40x speedup.
- Runtime inventory: 67 registered executor tools, 29 governed bio/workflow tools, 5 deterministic analysis routes.
- Research graph qualification: 8 frozen curated research scenarios, entity/event-relation F1 100%, effective-time accuracy 100%, evidence coverage 100%, score 100/100.
- BixBench Verified-50: initial BioCoreAgent run 22/50 (44.0%) -> best verified run 38/50 (76.0%), +32 percentage points.

## Claim Boundaries

- Memory metrics are a controlled retrieval correctness suite with explicit markers; they are not an open-domain semantic QA score.
- Research graph metrics qualify the frozen curated engineering scenarios only; they are not real-user or open-domain extraction evidence.
- Context correctness means current-request/latest-evidence retention and budget compliance, not LLM answer accuracy.
- BixBench uses the local runner's direct/local verifier. No official external LLM judge score is claimed.
- The 44% baseline is the initial BioCoreAgent Verified-50 run, not a raw foundation-model score.

## Evidence Files

- `artifacts/harness-regression-v2.json`
- `artifacts/resume-metrics-v1.json`
- `artifacts/research-graph-curated-v1.json`
- `F:/aicoding/bixbench_runs/verified50-deepseekchat-v1/bixbench_report.json`
- `F:/aicoding/bixbench_runs/verified50-deepseekchat-v10-full/bixbench_report.json`
