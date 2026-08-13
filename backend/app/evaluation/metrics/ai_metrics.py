"""
AI 调用质量 & Agent 工具统计指标(Sprint 8.5)

完全基于已有表做只读聚合:
- AIRequestLog: 稳定性 / 性能 / Token 消耗
- ReviewReport / GeneratedContract / GeneratedProposal 的 trace_summary: Agent 工具调用统计

设计原则:
- 不修改任何业务表, 仅 SELECT 读
- 复用现有 evaluation_service 中的核心函数(P95/Rate)
- 返回 dict 结构, 便于报告模板直接渲染
"""
from __future__ import annotations

from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Dict, Any, List


def _time_filter(query, column, start, end):
    return query.filter(column >= start).filter(column <= end)


def _p95(values):
    if not values:
        return None
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 1:
        return sorted_v[0]
    idx = 0.95 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return int(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * frac)


def _p50(values):
    if not values:
        return None
    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    if n % 2:
        return sorted_v[mid]
    return int((sorted_v[mid - 1] + sorted_v[mid]) / 2)


def _avg(values):
    return int(sum(values) / len(values)) if values else 0


def _rate(success, total):
    return round(success / total, 4) if total > 0 else 0.0


# ============================================================
# 1. 调用稳定性 & 性能 & Token
# ============================================================
def analyze_ai_request_logs(
    db_session,
    AIRequestLog,
    period_days: int = 30,
    period_end: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    统计 AIRequestLog: 总览 + 按 agent_type 分组。
    """
    now = period_end or datetime.utcnow()
    period_start = now - timedelta(days=period_days)

    rows = (
        _time_filter(AIRequestLog.query, AIRequestLog.created_time, period_start, now)
        .all()
    )

    total = len(rows)
    success = sum(1 for r in rows if r.status == 'success')
    failed = total - success
    latencies = [r.latency_ms for r in rows if r.latency_ms]
    in_toks = [r.input_tokens for r in rows if r.input_tokens is not None]
    out_toks = [r.output_tokens for r in rows if r.output_tokens is not None]
    tot_toks = [r.total_tokens for r in rows if r.total_tokens is not None]

    overview = {
        'period_start': period_start.strftime('%Y-%m-%d %H:%M:%S'),
        'period_end': now.strftime('%Y-%m-%d %H:%M:%S'),
        'total_calls': total,
        'success_count': success,
        'failed_count': failed,
        'success_rate': _rate(success, total),
        'avg_latency_ms': _avg(latencies),
        'p50_latency_ms': _p50(latencies),
        'p95_latency_ms': _p95(latencies),
        'avg_input_tokens': _avg(in_toks),
        'avg_output_tokens': _avg(out_toks),
        'avg_total_tokens': _avg(tot_toks),
        'sum_input_tokens': sum(in_toks),
        'sum_output_tokens': sum(out_toks),
        'sum_total_tokens': sum(tot_toks) or (sum(in_toks) + sum(out_toks)),
    }

    # ---- 按 agent_type 分组 ----
    per_agent = {}
    agent_types = sorted(set(r.agent_type for r in rows))
    for at in agent_types:
        sub = [r for r in rows if r.agent_type == at]
        lats = [r.latency_ms for r in sub if r.latency_ms]
        tts = [r.total_tokens for r in sub if r.total_tokens is not None]
        scs = sum(1 for r in sub if r.status == 'success')
        per_agent[at] = {
            'calls': len(sub),
            'success': scs,
            'failed': len(sub) - scs,
            'success_rate': _rate(scs, len(sub)),
            'avg_latency_ms': _avg(lats),
            'p95_latency_ms': _p95(lats),
            'avg_total_tokens': _avg(tts),
        }
    overview['per_agent'] = per_agent

    # ---- 失败原因 Top ----
    failed_reasons = defaultdict(int)
    for r in rows:
        if r.status == 'failed' and r.error_message:
            reason = (r.error_message or '').strip()
            if len(reason) > 80:
                reason = reason[:80] + '...'
            failed_reasons[reason or 'unknown'] += 1
    overview['failure_breakdown'] = sorted(
        [{'reason': k, 'count': v} for k, v in failed_reasons.items()],
        key=lambda x: x['count'], reverse=True,
    )[:10]

    return overview


# ============================================================
# 2. Agent 工具调用统计 (contract_review / generation / bid)
# ============================================================
def analyze_agent_tools(
    db_session,
    models: List[Any],   # [ReviewReport, GeneratedContract, GeneratedProposal]
    period_days: int = 30,
    period_end: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    从 3 张业务报表的 trace_summary.tool_stats 聚合工具调用统计。
    """
    now = period_end or datetime.utcnow()
    period_start = now - timedelta(days=period_days)

    total_calls = success_calls = failed_calls = 0
    per_tool = defaultdict(lambda: {'calls': 0, 'success': 0, 'failed': 0, 'duration_ms': 0})
    per_report_type = {}

    for M in models:
        ts_col = getattr(M, 'created_time', None)
        if ts_col is None:
            continue
        try:
            rows = _time_filter(M.query, ts_col, period_start, now).all()
        except Exception:
            continue
        type_name = M.__name__
        type_calls = type_success = type_failed = 0
        for r in rows:
            ts = getattr(r, 'trace_summary', None)
            if not isinstance(ts, dict):
                continue
            tool_stats = ts.get('tool_stats') or ts.get('trace_summary') or {}
            if not isinstance(tool_stats, dict):
                continue
            c = int(tool_stats.get('tool_call_count') or 0)
            s = int(tool_stats.get('tool_success_count') or 0)
            f = int(tool_stats.get('tool_failed_count') or 0)
            total_calls += c
            success_calls += s
            failed_calls += f
            type_calls += c
            type_success += s
            type_failed += f
            breakdown = tool_stats.get('tool_breakdown') or []
            if isinstance(breakdown, list):
                for b in breakdown:
                    if not isinstance(b, dict):
                        continue
                    name = b.get('tool') or 'unknown'
                    per_tool[name]['calls'] += int(b.get('calls') or 0)
                    per_tool[name]['success'] += int(b.get('success') or 0)
                    per_tool[name]['failed'] += int(b.get('failed') or 0)
                    per_tool[name]['duration_ms'] += int(
                        b.get('total_duration_ms') or b.get('duration_ms') or 0
                    )
        per_report_type[type_name] = {
            'tool_calls': type_calls,
            'success': type_success,
            'failed': type_failed,
            'success_rate': _rate(type_success, type_calls),
            'report_count': len(rows),
        }

    breakdown_list = []
    for name, v in per_tool.items():
        breakdown_list.append({
            'tool': name,
            'calls': v['calls'],
            'success': v['success'],
            'failed': v['failed'],
            'success_rate': _rate(v['success'], v['calls']),
            'total_duration_ms': v['duration_ms'],
        })
    breakdown_list.sort(key=lambda x: x['calls'], reverse=True)

    # ---- Agent 完成率 (按 trace_summary.success / report status 综合) ----
    task_total = 0
    task_success = 0
    for M in models:
        ts_col = getattr(M, 'created_time', None)
        if ts_col is None:
            continue
        try:
            rows = _time_filter(M.query, ts_col, period_start, now).all()
        except Exception:
            continue
        for r in rows:
            st = getattr(r, 'status', None)
            ts = getattr(r, 'trace_summary', None) if hasattr(r, 'trace_summary') else None
            task_total += 1
            ok = False
            if st in ('success', 'completed', 'approved'):
                ok = True
            elif isinstance(ts, dict):
                tc = int((ts.get('tool_stats') or {}).get('tool_failed_count') or 0)
                if tc == 0:
                    ok = True
            if ok:
                task_success += 1

    return {
        'total_tool_calls': total_calls,
        'tool_success_count': success_calls,
        'tool_failed_count': failed_calls,
        'tool_success_rate': _rate(success_calls, total_calls),
        'tool_breakdown': breakdown_list,
        'per_report_type': per_report_type,
        'task_total_count': task_total,
        'task_success_count': task_success,
        'task_completion_rate': _rate(task_success, task_total),
    }


# ============================================================
# 3. 成本估算 (DeepSeek 价目表)
# ============================================================
def estimate_cost(
    sum_input_tokens: int,
    sum_output_tokens: int,
    input_cny_per_million: float = 0.14,
    output_cny_per_million: float = 0.28,
) -> Dict[str, Any]:
    """粗略估算人民币成本。"""
    in_cost = round(sum_input_tokens * input_cny_per_million / 1_000_000, 4)
    out_cost = round(sum_output_tokens * output_cny_per_million / 1_000_000, 4)
    return {
        'input_tokens': sum_input_tokens,
        'output_tokens': sum_output_tokens,
        'input_cost_rmb': in_cost,
        'output_cost_rmb': out_cost,
        'total_cost_rmb': round(in_cost + out_cost, 4),
        'price_remark': 'DeepSeek-V3: 0.14元/百万input, 0.28元/百万output(仅供参考)',
    }
