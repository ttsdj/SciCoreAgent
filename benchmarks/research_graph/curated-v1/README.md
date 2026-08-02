# Curated Research Graph Qualification v1

该冻结集包含 8 个独立编写并人工标注的科研工程场景，覆盖研究决策、软件异常、恢复、阈值替代、产物血缘、用户偏好和单细胞输入。

它用于验证实体归一化、事件分类、有效时间、异常/恢复关系和证据回跳链路。该数据集是工程资格集，不是真实用户自然对话，也不能用于宣称开放域知识图谱抽取准确率。

验收门槛：

- 所有预期证据均能定位。
- 事件类型无错误。
- 加权总分不低于 80/100。

复现：

```powershell
python scripts/evaluate_research_graph.py `
  benchmarks/research_graph/curated-v1/cases.jsonl `
  --output artifacts/research-graph-curated-v1.json
```
