"""
评估状态判定 + Summary 结构化输出(Sprint 8.5 优化)

引入三态评估:
- PASS:    所有指标达标
- PENDING: 知识库无文档命中,无法真实评估 RAG(状态待数据补全后再判定)
- FAIL:    有上下文命中但指标未达标 / AI 调用稳定性不达标

规则:
1. RAG 评估:
   - context_hit_count == 0 → status=PENDING,reason="当前知识库无匹配文档,无法评价 RAG 真实性"
   - context_hit_count > 0  → 按 faithfulness/relevancy/precision/recall 是否达标判定 PASS/FAIL
2. AI 调用稳定性:
   - success_rate < 0.95 → status=FAIL (与 RAG 状态取最严)
3. 性能:
   - p95_latency_ms >= 10000 → status=FAIL
4. 综合状态:取三者最严(WARN > FAIL > PENDING > PASS)
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional


# 评估状态严重度排序(数字越大越严重)
_STATUS_SEVERITY = {'PASS': 0, 'PENDING': 1, 'FAIL': 2}
_STATUS_LABELS = {
    'PASS': '达标',
    'PENDING': '待数据补全',
    'FAIL': '未达标',
}


def _pick_worst(a: str, b: str) -> str:
    """取两个状态中较严重者。"""
    return a if _STATUS_SEVERITY.get(a, 1) >= _STATUS_SEVERITY.get(b, 1) else b


# ============================================================
# RAG 状态判定
# ============================================================
def judge_rag_status(
    context_hit_count: int,
    total_questions: int,
    mean_scores: Dict[str, float],
    targets: Dict[str, float],
) -> Dict[str, Any]:
    """
    判定 RAG 评估状态。

    :param context_hit_count: 有上下文召回的样本数
    :param total_questions: 总样本数
    :param mean_scores: {faithfulness, answer_relevancy, context_precision, context_recall} 均值
    :param targets: 4 指标目标值
    :return: {status, reason, details}
    """
    # PENDING: 知识库无任何命中,无法评价 RAG
    if context_hit_count == 0:
        return {
            'status': 'PENDING',
            'reason': '当前知识库无匹配文档,无法评价 RAG 真实性。请先上传合同/法规/案例知识文档后重新评估。',
            'context_hit_rate': 0.0,
            'details': {
                'total_questions': total_questions,
                'context_hit_count': 0,
                'mean_scores': mean_scores,
                'targets': targets,
                'note': '所有指标基于空上下文计算,数值无业务意义,仅作链路连通性证明。',
            },
        }

    # 有命中:按 4 指标是否达标判定
    failed_metrics = []
    for k, target in targets.items():
        actual = mean_scores.get(k, 0.0) or 0.0
        if actual < target:
            failed_metrics.append({
                'metric': k,
                'actual': round(actual, 4),
                'target': target,
                'gap': round(target - actual, 4),
            })
    hit_rate = round(context_hit_count / total_questions, 4) if total_questions > 0 else 0.0
    if not failed_metrics:
        return {
            'status': 'PASS',
            'reason': f'所有 RAG 指标达标(命中率 {hit_rate:.1%})。',
            'context_hit_rate': hit_rate,
            'details': {
                'total_questions': total_questions,
                'context_hit_count': context_hit_count,
                'mean_scores': mean_scores,
                'targets': targets,
            },
        }
    return {
        'status': 'FAIL',
        'reason': f'{len(failed_metrics)} 项 RAG 指标未达标: '
                  + ', '.join(f"{m['metric']}({m['actual']}<{m['target']})" for m in failed_metrics),
        'context_hit_rate': hit_rate,
        'details': {
            'total_questions': total_questions,
            'context_hit_count': context_hit_count,
            'mean_scores': mean_scores,
            'targets': targets,
            'failed_metrics': failed_metrics,
        },
    }


# ============================================================
# AI 调用稳定性状态判定
# ============================================================
def judge_ai_stability(
    total_calls: int,
    success_rate: float,
    p95_latency_ms: Optional[int],
    targets: Dict[str, Any],
) -> Dict[str, Any]:
    """
    判定 AI 调用稳定性状态。

    :return: {status, reason, details}
    """
    if total_calls == 0:
        return {
            'status': 'PENDING',
            'reason': 'AIRequestLog 暂无调用记录,无法评估稳定性。',
            'details': {'total_calls': 0, 'note': '请先执行合同审核/生成/RAG 问答触发 AI 调用。'},
        }

    reasons = []
    sr_target = targets.get('success_rate', 0.95)
    p95_target = targets.get('p95_latency_ms', 10000)

    if success_rate < sr_target:
        reasons.append(
            f'成功率 {success_rate:.1%} < 目标 {sr_target:.0%}'
        )
    if p95_latency_ms is not None and p95_latency_ms >= p95_target:
        reasons.append(
            f'P95 {p95_latency_ms}ms ≥ 目标 {p95_target}ms'
        )

    if not reasons:
        return {
            'status': 'PASS',
            'reason': f'稳定性达标(成功率 {success_rate:.1%},P95 {p95_latency_ms}ms)。',
            'details': {
                'total_calls': total_calls,
                'success_rate': success_rate,
                'p95_latency_ms': p95_latency_ms,
                'targets': targets,
            },
        }
    return {
        'status': 'FAIL',
        'reason': '稳定性不达标: ' + '; '.join(reasons),
        'details': {
            'total_calls': total_calls,
            'success_rate': success_rate,
            'p95_latency_ms': p95_latency_ms,
            'targets': targets,
            'failed_items': reasons,
        },
    }


# ============================================================
# 综合状态(取最严)
# ============================================================
def overall_status(rag: Dict, ai: Dict) -> Dict[str, Any]:
    """综合 RAG + AI 稳定性,取最严状态。"""
    worst = _pick_worst(rag['status'], ai['status'])
    reasons = []
    if rag['status'] != 'PASS':
        reasons.append(f'[RAG] {rag["reason"]}')
    if ai['status'] != 'PASS':
        reasons.append(f'[AI] {ai["reason"]}')
    return {
        'status': worst,
        'status_label': _STATUS_LABELS.get(worst, worst),
        'reason': ' | '.join(reasons) if reasons else '所有指标达标。',
    }


# ============================================================
# 任务3:evaluation_summary.json 结构化输出
# ============================================================
def build_summary(
    rag_eval: Dict[str, Any],
    ai_stats: Dict[str, Any],
    knowledge_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """
    生成 evaluation_summary 结构(用于 /api/v1/evaluation/summary 接口 + 落盘 JSON)。

    :param rag_eval: run_rag_evaluation() 返回值
    :param ai_stats: do_ai_metrics() 返回值
    :param knowledge_stats: {total_documents, hit_documents, embedding_completed}
    :return: dict
    """
    targets = {
        'faithfulness': 0.85,
        'answer_relevancy': 0.85,
        'context_precision': 0.80,
        'context_recall': 0.80,
    }
    ai_targets = {'success_rate': 0.95, 'p95_latency_ms': 10_000}

    rag_all = rag_eval.get('aggregate_all', {}).get('mean', {})
    ai_overview = ai_stats.get('ai_overview', {})
    tools = ai_stats.get('agent_tools', {})
    cost = ai_stats.get('cost', {})

    # RAG 状态判定
    rag_status = judge_rag_status(
        context_hit_count=rag_eval.get('samples_with_context', 0),
        total_questions=rag_eval.get('sample_count', 0),
        mean_scores=rag_all,
        targets=targets,
    )

    # AI 稳定性状态判定
    ai_status = judge_ai_stability(
        total_calls=ai_overview.get('total_calls', 0),
        success_rate=ai_overview.get('success_rate', 0.0),
        p95_latency_ms=ai_overview.get('p95_latency_ms'),
        targets=ai_targets,
    )

    overall = overall_status(rag_status, ai_status)

    return {
        'version': 'v1.0.0-RC',
        'generated_at': rag_eval.get('evaluated_at'),
        # Sprint 8.6 收尾: 评估模式与 Answer 生成策略(区分开发调参/发布验收)
        'evaluation_mode': rag_eval.get('evaluation_mode', 'quick'),
        'answer_generation': rag_eval.get('answer_generation', 'ground_truth'),
        'total_questions': rag_eval.get('sample_count', 0),
        'context_hit_count': rag_eval.get('samples_with_context', 0),
        'context_hit_rate': rag_status.get('context_hit_rate', 0.0),

        # RAG 4 指标
        'faithfulness': rag_all.get('faithfulness', 0.0),
        'answer_relevancy': rag_all.get('answer_relevancy', 0.0),
        'context_precision': rag_all.get('context_precision', 0.0),
        'context_recall': rag_all.get('context_recall', 0.0),

        # AI 稳定性
        'ai_total_calls': ai_overview.get('total_calls', 0),
        'ai_success_rate': ai_overview.get('success_rate', 0.0),
        'ai_p95_latency_ms': ai_overview.get('p95_latency_ms'),

        # 成本
        'total_tokens': ai_overview.get('sum_total_tokens', 0),
        'estimated_cost_rmb': cost.get('total_cost_rmb', 0.0),

        # Agent 工具
        'agent_task_total': tools.get('task_total_count', 0),
        'agent_completion_rate': tools.get('task_completion_rate', 0.0),
        'tool_call_total': tools.get('total_tool_calls', 0),
        'tool_success_rate': tools.get('tool_success_rate', 0.0),

        # 测试环境说明
        'test_environment': {
            'knowledge_total_documents': knowledge_stats.get('total_documents', 0),
            'knowledge_hit_documents': knowledge_stats.get('hit_documents', 0),
            'knowledge_embedding_completed': knowledge_stats.get('embedding_completed', 0),
            'knowledge_hit_rate': knowledge_stats.get('hit_rate', 0.0),
            'embedding_model': 'BAAI/bge-small-zh-v1.5',
            'llm_model': 'DeepSeek (deepseek-chat)',
            'retriever': 'DenseRetriever(TopK=5, Threshold=0.35)',
            'vector_store': 'FAISS IndexFlatIP + IndexIDMap2',
        },

        # Sprint 8.7: 性能统计(各阶段耗时 + cache 命中率,定位评估瓶颈)
        'performance': rag_eval.get('performance', {}),

        # 综合状态
        'status': overall['status'],
        'status_label': overall['status_label'],
        'reason': overall['reason'],

        # 子状态详情
        'rag_status': rag_status,
        'ai_status': ai_status,

        # 原始聚合(供详情查看)
        'rag_aggregate': rag_eval.get('aggregate_all', {}),
        'rag_per_category': rag_eval.get('per_category', {}),
        'ai_per_agent': ai_overview.get('per_agent', {}),
        'agent_tool_breakdown': tools.get('tool_breakdown', []),

        # Sprint 8.9: 知识覆盖诊断(Retriever Hit ≠ Knowledge Coverage)
        # 明确区分"召回到了内容"与"召回到了正确知识"
        'knowledge_coverage': rag_eval.get('knowledge_coverage', {}),
        'aggregate_by_coverage': rag_eval.get('aggregate_by_coverage', {}),
    }
