"""
AI 评估服务(Sprint 8 - v1.0.0 企业级 AI 增强)

职责:
- 基于 AIRequestLog / OperationLog / 3 张业务报表(ReviewReport/GeneratedContract/GeneratedProposal)的
  trace_summary 字段,聚合生成 AI 运行评估报告(只读,不修改业务表)
- 支持 report 持久化为 EvaluationReport 快照(POST /evaluation/report 后保存,便于历史回溯)

指标组成:
- rag        : call_count / success / failed / success_rate / avg_latency / p95_latency / avg_tokens
- agent      : 按 contract_review/generation/bid 分组的 success_rate / avg_latency / avg_tokens
- tool       : total_calls / success / failed / success_rate / breakdown[{tool,calls,success,failed,total_duration_ms}]
- cost       : input_tokens / output_tokens / total_tokens / estimated_rmb(粗略按 2RMB / 1M output tokens)
- operation  : total / failed / failure_rate / breakdown[{operation_type,count,failed,failure_rate}]

设计原则:
- 所有指标只读已有表;新增写仅 EvaluationReport 本身,绝不修改 Sprint 0-7 数据
- 空数据返回 0/None,不抛出;接口始终返回成功(查询范围大也不会失败)
- p95 使用近 2000 条排序近似(不依赖 numpy,保持纯标准库)
"""
from datetime import datetime, timedelta
from collections import defaultdict

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.ai_request_log import AIRequestLog
from app.models.operation_log import OperationLog
from app.models.review_report import ReviewReport
from app.models.generated_contract import GeneratedContract
from app.models.generated_proposal import GeneratedProposal
from app.models.evaluation_report import EvaluationReport


# 粗略成本估算(DeepSeek-V3-Chat 大约 0.14 元 / 百万 input,0.28 元 / 百万 output)
# 为避免浮动大,这里给出粗估值:0.2 RMB per 1M output tokens
_RMB_PER_1M_OUTPUT = 0.2
_RMB_PER_1M_INPUT = 0.1


def generate_metrics(period_start=None, period_end=None):
    """
    生成实时评估指标(不持久化)。

    :param period_start: datetime,可 None(默认近 30 天)
    :param period_end:   datetime,可 None
    :return: dict 指标(完整的 5 大类)
    """
    now = datetime.utcnow()
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = now - timedelta(days=30)

    rag = _rag_metrics(period_start, period_end)
    agent = _agent_metrics(period_start, period_end)
    tool = _tool_metrics(period_start, period_end)
    cost = _cost_metrics(period_start, period_end)
    operation = _operation_metrics(period_start, period_end)

    return {
        'period_start': period_start.strftime('%Y-%m-%d %H:%M:%S'),
        'period_end': period_end.strftime('%Y-%m-%d %H:%M:%S'),
        'rag': rag,
        'agent': agent,
        'tool': tool,
        'cost': cost,
        'operation': operation,
    }


def generate_report(period_start=None, period_end=None, user_id=None, persist=True):
    """
    生成评估报告 + 可选持久化为 EvaluationReport。

    :return: dict 含 report_no + metrics + summary
    """
    metrics = generate_metrics(period_start, period_end)
    summary = _summarize(metrics)

    report_dict = None
    if persist:
        try:
            rpt = EvaluationReport(
                period_start=period_start,
                period_end=period_end,
                metrics=metrics,
                summary=summary,
                generated_by=user_id,
            )
            db.session.add(rpt)
            db.session.commit()
            report_dict = rpt.to_dict(include_metrics=True)
        except Exception as e:
            db.session.rollback()
            logger.warning('[Evaluation] 持久化失败,返回内存结果: %s', e)

    if report_dict is None:
        report_dict = {
            'report_no': f'EVAL-TMP-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
            'period_start': metrics['period_start'],
            'period_end': metrics['period_end'],
            'summary': summary,
            'metrics': {k: v for k, v in metrics.items() if k not in ('period_start', 'period_end')},
            'generated_by': user_id,
            'created_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'persisted': False,
        }
    return report_dict


def list_reports(page=1, size=20):
    page, size = _normalize_paging(page, size)
    total = EvaluationReport.query.count()
    items = (
        EvaluationReport.query.order_by(EvaluationReport.created_time.desc())
        .offset((page - 1) * size).limit(size).all()
    )
    return {
        'total': total, 'page': page, 'size': size,
        'items': [r.to_dict(include_metrics=False) for r in items],
    }


def get_report(report_id):
    try:
        rid = int(report_id)
    except (TypeError, ValueError):
        return None
    rpt = db.session.get(EvaluationReport, rid)
    return rpt.to_dict(include_metrics=True) if rpt else None


# ============================================================
# 指标聚合(内部)
# ============================================================
def _time_filter(query, model, column, start, end):
    return query.filter(column >= start).filter(column <= end)


def _p95(values):
    if not values:
        return None
    sorted_v = sorted(values)
    # 经典 95 分位:index = 0.95*(N-1),取线性插值
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    idx = 0.95 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return int(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * frac)


def _avg(values):
    return int(sum(values) / len(values)) if values else 0


def _rate(success, total):
    return round(success / total, 4) if total > 0 else 0.0


def _rag_metrics(start, end):
    rows = _time_filter(AIRequestLog.query, AIRequestLog, AIRequestLog.created_time, start, end)\
        .filter_by(agent_type='rag').all()
    call_count = len(rows)
    success = sum(1 for r in rows if r.status == 'success')
    failed = call_count - success
    latencies = [r.latency_ms for r in rows if r.latency_ms]
    tokens = [r.total_tokens for r in rows if r.total_tokens]
    return {
        'call_count': call_count,
        'success_count': success,
        'failed_count': failed,
        'success_rate': _rate(success, call_count),
        'avg_latency_ms': _avg(latencies),
        'p95_latency_ms': _p95(latencies),
        'avg_total_tokens': _avg(tokens),
    }


def _agent_metrics(start, end):
    agent_types = ('contract_review', 'generation', 'bid')
    result = {}
    for at in agent_types:
        rows = _time_filter(AIRequestLog.query, AIRequestLog, AIRequestLog.created_time, start, end)\
            .filter_by(agent_type=at).all()
        total = len(rows)
        success = sum(1 for r in rows if r.status == 'success')
        failed = total - success
        lats = [r.latency_ms for r in rows if r.latency_ms]
        toks = [r.total_tokens for r in rows if r.total_tokens]
        result[at] = {
            'total': total,
            'success': success,
            'failed': failed,
            'success_rate': _rate(success, total),
            'avg_latency_ms': _avg(lats),
            'avg_total_tokens': _avg(toks),
        }
    return result


def _tool_metrics(start, end):
    """从 ReviewReport/GeneratedContract/GeneratedProposal 的 trace_summary.tool_stats 聚合。

    每个 report 的 trace_summary.tool_stats 含:
        total_calls, success_count, failed_count,
        tool_breakdown: [{tool, calls, success, failed, total_duration_ms}]
    """
    total_calls = success_calls = failed_calls = 0
    per_tool = defaultdict(lambda: {'calls': 0, 'success': 0, 'failed': 0, 'total_duration_ms': 0})
    models = (ReviewReport, GeneratedContract, GeneratedProposal)
    for M in models:
        try:
            ts_col = getattr(M, 'started_time', M.created_time) if hasattr(M, 'started_time') else M.created_time
        except Exception:
            ts_col = M.created_time
        try:
            rows = _time_filter(M.query, M, ts_col, start, end).all()
        except Exception:
            continue
        for r in rows:
            ts = getattr(r, 'trace_summary', None)
            if not isinstance(ts, dict):
                continue
            tstats = ts.get('tool_stats') or {}
            if not isinstance(tstats, dict):
                continue
            total_calls += int(tstats.get('tool_call_count') or 0)
            success_calls += int(tstats.get('tool_success_count') or 0)
            failed_calls += int(tstats.get('tool_failed_count') or 0)
            breakdown = tstats.get('tool_breakdown') or []
            if not isinstance(breakdown, list):
                continue
            for b in breakdown:
                if not isinstance(b, dict):
                    continue
                name = b.get('tool') or 'unknown'
                per_tool[name]['calls'] += int(b.get('calls') or 0)
                per_tool[name]['success'] += int(b.get('success') or 0)
                per_tool[name]['failed'] += int(b.get('failed') or 0)
                per_tool[name]['total_duration_ms'] += int(b.get('total_duration_ms') or b.get('duration_ms') or 0)
    breakdown_list = []
    for name, v in per_tool.items():
        calls = v['calls']
        success = v['success']
        failed = v['failed']
        breakdown_list.append({
            'tool': name,
            'calls': calls,
            'success': success,
            'failed': failed,
            'success_rate': _rate(success, calls),
            'total_duration_ms': v['total_duration_ms'],
        })
    breakdown_list.sort(key=lambda x: x['calls'], reverse=True)
    return {
        'total_calls': total_calls,
        'success_count': success_calls,
        'failed_count': failed_calls,
        'success_rate': _rate(success_calls, total_calls),
        'breakdown': breakdown_list,
    }


def _cost_metrics(start, end):
    rows = _time_filter(AIRequestLog.query, AIRequestLog, AIRequestLog.created_time, start, end).all()
    in_tok = sum(int(r.input_tokens or 0) for r in rows)
    out_tok = sum(int(r.output_tokens or 0) for r in rows)
    tot = sum(int(r.total_tokens or 0) for r in rows)
    if tot == 0:
        # 兜底加总
        tot = in_tok + out_tok
    estimated_rmb = round(
        (in_tok * _RMB_PER_1M_INPUT + out_tok * _RMB_PER_1M_OUTPUT) / 1_000_000,
        4,
    )
    return {
        'input_tokens': in_tok,
        'output_tokens': out_tok,
        'total_tokens': tot,
        'estimated_rmb': estimated_rmb,
    }


def _operation_metrics(start, end):
    rows = _time_filter(OperationLog.query, OperationLog, OperationLog.created_time, start, end).all()
    total = len(rows)
    failed = sum(1 for r in rows if r.status == 'failed')
    per_op = defaultdict(lambda: {'count': 0, 'failed': 0})
    for r in rows:
        op = r.operation_type or 'unknown'
        per_op[op]['count'] += 1
        if r.status == 'failed':
            per_op[op]['failed'] += 1
    breakdown = []
    for op, v in per_op.items():
        c = v['count']
        f = v['failed']
        breakdown.append({
            'operation_type': op,
            'count': c,
            'failed': f,
            'failure_rate': _rate(f, c),
        })
    breakdown.sort(key=lambda x: x['count'], reverse=True)
    return {
        'total': total,
        'failed': failed,
        'failure_rate': _rate(failed, total),
        'breakdown': breakdown,
    }


def _summarize(m):
    """生成人类可读摘要(中文,一行概览 + 3 点关键指标)。"""
    rag = m['rag']
    cost = m['cost']
    op = m['operation']
    agent = m['agent'] or {}
    overall_agent_total = sum(a.get('total', 0) for a in agent.values())
    overall_agent_success = sum(a.get('success', 0) for a in agent.values())
    lines = []
    lines.append(
        f"AI 评估区间 {m['period_start']} ~ {m['period_end']}: "
        f"Agent 总调用 {overall_agent_total}, 成功率 {_rate(overall_agent_success, overall_agent_total):.1%}。"
    )
    lines.append(
        f"RAG: {rag['call_count']} 次, 平均 {rag['avg_latency_ms']}ms, P95 {rag['p95_latency_ms'] or 0}ms。"
    )
    lines.append(
        f"成本估算: {cost['total_tokens']} tokens, ≈ ¥{cost['estimated_rmb']}。"
    )
    lines.append(
        f"系统操作: {op['total']} 次, 失败 {op['failed']}, 失败率 {op['failure_rate']:.1%}。"
    )
    return '\n'.join(lines)


def _normalize_paging(page, size):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(int(size), 100))
    except (TypeError, ValueError):
        size = 20
    return page, size
