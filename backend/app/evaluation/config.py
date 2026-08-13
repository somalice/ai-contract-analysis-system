"""
AI 验收评估配置(Sprint 8.5 - v1.0.0 RC)

目标阈值与企业上线标准对齐:
- Faithfulness >= 0.85 : 回答必须忠实于检索上下文,避免幻觉
- Answer Relevancy >= 0.85 : 回答必须解决用户问题
- Context Precision >= 0.80 : 召回内容必须相关
- Context Recall >= 0.80 : 必须召回完整支持信息
- AI 调用成功率 >= 95%
- P95 latency < 10s
"""
from __future__ import annotations


# ========== RAG 评估目标阈值 ==========
RAG_TARGETS = {
    'faithfulness': 0.85,
    'answer_relevancy': 0.85,
    'context_precision': 0.80,
    'context_recall': 0.80,
}

# ========== AI 调用质量目标 ==========
AI_STABILITY_TARGETS = {
    'success_rate': 0.95,          # 成功率 >= 95%
    'p95_latency_ms': 10_000,      # P95 < 10s
}

# ========== RAG 评估运行配置 ==========
RAG_EVAL_CONFIG = {
    # 采样: 如数据集过大,随机取 N 条(节省时间/成本);设 None 则全量
    'sample_size': None,
    # Retriever TopK: 与生产一致,不改变召回策略
    'retriever_top_k': 5,
    # 分数阈值: 与生产参数一致
    'score_threshold': 0.35,
    # 如 DeepSeek API 不可用,降级为 LLM-as-a-Judge 关闭,仅跑检索指标
    'allow_llm_judge_fallback': True,
    # 每条 LLM 判断的超时秒数(避免单条卡住)
    'per_item_timeout_s': 30,
    # 最大重试次数(网络波动)
    'max_retries': 2,
}

# ========== 成本估算(DeepSeek 公开价目表) ==========
COST_CONFIG = {
    # 单位: 元 / 百万 tokens
    'input_tokens_cny_per_million': 0.14,
    'output_tokens_cny_per_million': 0.28,
}

# ========== 报告输出路径 ==========
REPORT_PATHS = {
    'ai_acceptance_report': 'docs/AI_ACCEPTANCE_REPORT.md',
    'sprint85_report': 'docs/SPRINT8_5_AI_EVALUATION_REPORT.md',
}

# ========== 统一聚合 ==========
EVAL_CONFIG = {
    'rag_targets': RAG_TARGETS,
    'ai_stability_targets': AI_STABILITY_TARGETS,
    'rag_eval': RAG_EVAL_CONFIG,
    'cost': COST_CONFIG,
    'report_paths': REPORT_PATHS,
    'version': 'v1.0.0-RC',
}
