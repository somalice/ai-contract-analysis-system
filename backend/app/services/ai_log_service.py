"""
AI 调用日志服务(Sprint 8 - v1.0.0 企业级 AI 增强)

职责:
- log_agent_run:在 3 个 Agent Service(review/generation/proposal)的 commit 后钩子调用,落库 AIRequestLog
- log_rag_call:在 rag_service.query_rag 结束后调用,记录 RAG LLM 调用
- list_ai_logs / get_ai_log:供 Logs API 查询

设计原则:
- **所有 public 方法永不抛出**:任何失败(DB 异常、数据异常)→ logger.warning,不影响主业务流程
- 调用方(Services)通过 try/except 包裹,再次兜底(双重保险)
- 不访问 request 对象:所有上下文(user_id/prompt_version)由调用方传入
"""
from datetime import datetime
from typing import Optional

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.ai_request_log import AIRequestLog


def _commit_safe():
    """提交 DB,失败 rollback + warning,不抛出"""
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.warning('[AILog] commit 失败: %s', e)
        return False


# ============================================================
# 写入接口
# ============================================================
def log_agent_run(user_id, agent_type, model, prompt_version,
                  agent_result, related_id, related_type,
                  latency_ms: int,
                  trace_summary=None,
                  extra_tokens=None):
    """
    记录一次 Agent 运行(ContractReview / Generation / Bid Proposal)。

    :param agent_result: AgentResult / GenerationResult / ProposalResult 或类似对象:
        需可读取:
            .status  (success/failed)
            .llm_error 或 .error_message (可选)
            .trace_summary (可选,Sprint 5/7 已输出 10 项指标)
    :param extra_tokens: 若 AgentResult 不含 token,从 llm_client.get_run_usage() 获取 {input_tokens,...}
    """
    try:
        status = 'success'
        error_message = None
        # 兼容多种 Result 对象(鸭子类型)
        agent_status = getattr(agent_result, 'status', None)
        if agent_status and str(agent_status).lower() in ('failed', 'error', 'fallback'):
            status = 'failed'
        llm_err = getattr(agent_result, 'llm_error', None) \
            or getattr(agent_result, 'error_message', None) \
            or getattr(agent_result, 'error', None)
        if llm_err:
            error_message = str(llm_err)[:5000]
            # LLM 有错误也标记 failed(即使 Agent 兜底 success 也反映调用失败)
            if status != 'failed' and error_message:
                status = 'failed'

        # Token:优先 AgentResult 内部的 trace_summary.llm_stats,否则 extra_tokens
        in_tok = out_tok = tot_tok = None
        ts = trace_summary or getattr(agent_result, 'trace_summary', None)
        if isinstance(ts, dict):
            llm_stats = ts.get('llm_stats') or {}
            if isinstance(llm_stats, dict):
                in_tok = _int_or_none(llm_stats.get('input_tokens') or llm_stats.get('input_token_sum'))
                out_tok = _int_or_none(llm_stats.get('output_tokens') or llm_stats.get('output_token_sum'))
                tot_tok = _int_or_none(llm_stats.get('total_tokens')) or (
                    (in_tok or 0) + (out_tok or 0) if (in_tok or out_tok) else None
                )
        if (in_tok is None and out_tok is None) and isinstance(extra_tokens, dict):
            in_tok = _int_or_none(extra_tokens.get('input_tokens')) or in_tok
            out_tok = _int_or_none(extra_tokens.get('output_tokens')) or out_tok
            tot_tok = _int_or_none(extra_tokens.get('total_tokens')) or (
                (in_tok or 0) + (out_tok or 0) if (in_tok or out_tok) else tot_tok
            )

        log = AIRequestLog(
            user_id=_int_or_none(user_id),
            agent_type=_truncate(agent_type, 32),
            model=_truncate(model, 64),
            prompt_version=_truncate(prompt_version, 32),
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            latency_ms=_int_or_none(latency_ms),
            status=_truncate(status, 16),
            error_message=error_message,
            trace_summary=ts,
            related_id=_int_or_none(related_id),
            related_type=_truncate(related_type, 32),
        )
        db.session.add(log)
        _commit_safe()
        return log.id
    except Exception as e:
        logger.warning('[AILog] log_agent_run 记录失败(不影响业务): agent=%s err=%s',
                       agent_type, e)
        # 极端场景 db.session 状态异常,稳妥 rollback
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


def log_rag_call(user_id, question, answer, latency_ms: int,
                 status: str, error_message=None, token_usage=None, trace_summary=None):
    """
    记录一次 RAG LLM 问答调用(单独 agent_type='rag')。

    token_usage: dict {input_tokens, output_tokens, total_tokens}
    """
    try:
        in_tok = out_tok = tot_tok = None
        if isinstance(token_usage, dict):
            in_tok = _int_or_none(token_usage.get('input_tokens'))
            out_tok = _int_or_none(token_usage.get('output_tokens'))
            tot_tok = _int_or_none(token_usage.get('total_tokens')) \
                or ((in_tok or 0) + (out_tok or 0) if (in_tok or out_tok) else None)

        if not isinstance(status, str) or status not in ('success', 'failed'):
            status = 'success' if status in ('success', True) else 'failed'

        log = AIRequestLog(
            user_id=_int_or_none(user_id),
            agent_type='rag',
            model=None,   # 由 RAG config 决定,可不传;后续可补
            prompt_version='rag_answer_v1',
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            latency_ms=_int_or_none(latency_ms),
            status=_truncate(status, 16),
            error_message=str(error_message)[:5000] if error_message else None,
            trace_summary=trace_summary,
            related_id=None,
            related_type=None,
        )
        db.session.add(log)
        _commit_safe()
        return log.id
    except Exception as e:
        logger.warning('[AILog] log_rag_call 记录失败: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


# ============================================================
# 查询接口(Log API 使用)
# ============================================================
def list_ai_logs(agent_type=None, status=None, user_id=None,
                 start_time=None, end_time=None, page=1, size=20):
    page, size = _normalize_paging(page, size)
    q = AIRequestLog.query
    if agent_type:
        q = q.filter_by(agent_type=agent_type)
    if status:
        q = q.filter_by(status=status)
    if user_id:
        q = q.filter_by(user_id=int(user_id))
    if start_time:
        q = q.filter(AIRequestLog.created_time >= start_time)
    if end_time:
        q = q.filter(AIRequestLog.created_time <= end_time)
    total = q.count()
    items = (
        q.order_by(AIRequestLog.created_time.desc())
        .offset((page - 1) * size).limit(size)
        .all()
    )
    return {
        'total': total,
        'page': page,
        'size': size,
        'items': [l.to_dict(include_trace_summary=True) for l in items],
    }


def get_ai_log(log_id):
    try:
        lid = int(log_id)
    except (TypeError, ValueError):
        return None
    log = db.session.get(AIRequestLog, lid)
    return log.to_dict(include_trace_summary=True) if log else None


# ============================================================
# utils
# ============================================================
def _int_or_none(v):
    if v is None:
        return None
    try:
        r = int(v)
        return r
    except (TypeError, ValueError):
        return None


def _truncate(v, n):
    if v is None:
        return None
    s = str(v)
    return s if len(s) <= n else s[:n]


def _normalize_paging(page, size):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(int(size), 200))
    except (TypeError, ValueError):
        size = 20
    return page, size
