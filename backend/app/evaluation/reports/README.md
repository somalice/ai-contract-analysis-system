# AI 评估报告目录(Sprint 8.5)

## 报告产物

本目录用于存放评估运行过程中的中间 JSON 结果。

最终验收报告输出到仓库根:

- `docs/AI_ACCEPTANCE_REPORT.md` : AI 能力验收报告(面向产品/QA,供封版决策)
- `docs/SPRINT8_5_AI_EVALUATION_REPORT.md` : Sprint 8.5 专项报告(面向开发,含变更清单与回归结论)

## 评估流水线

```
contract_qa_dataset.json (50+ QA)
        ↓
run_rag_eval.py  (Retriever → Context → LLM Answer)
        ↓
rag_metrics.py   (Faithfulness / Relevancy / Precision / Recall)
        ↓
ai_metrics.py    (稳定性 / 性能 P95 / Token 成本 / Agent Tool 统计)
        ↓
report_builder   → AI_ACCEPTANCE_REPORT.md
```

## 指标说明

| 指标 | 含义 | 目标 |
|------|------|------|
| Faithfulness | 回答是否来自检索内容(无幻觉) | ≥0.85 |
| Answer Relevancy | 回答是否解决用户问题 | ≥0.85 |
| Context Precision | 召回内容是否相关 | ≥0.80 |
| Context Recall | 是否召回完整支持信息 | ≥0.80 |
| Success Rate | AI 调用成功率 | ≥95% |
| P95 Latency | 95 分位响应时间 | <10s |
