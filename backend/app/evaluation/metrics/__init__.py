"""
metrics 包(Sprint 8.5)

- rag_metrics: RAG 4 指标评估 (Faithfulness / Relevancy / Precision / Recall)
- ai_metrics: AI 调用稳定性 + Agent 工具统计 + 成本估算
"""
from .rag_metrics import (
    evaluate_single_sample,
    aggregate_scores,
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from .ai_metrics import (
    analyze_ai_request_logs,
    analyze_agent_tools,
    estimate_cost,
)
from .status_judge import (
    judge_rag_status,
    judge_ai_stability,
    overall_status,
    build_summary,
)

__all__ = [
    'evaluate_single_sample',
    'aggregate_scores',
    'faithfulness',
    'answer_relevancy',
    'context_precision',
    'context_recall',
    'analyze_ai_request_logs',
    'analyze_agent_tools',
    'estimate_cost',
    'judge_rag_status',
    'judge_ai_stability',
    'overall_status',
    'build_summary',
]
