"""
合同审核业务服务(Sprint 5 - v0.7.0)

职责:
- trigger_review:触发合同 AI 风险审核(建 ReviewReport + 同步执行 Agent)
- get_review:查询审核报告(含 risks 详情)
- list_contract_reviews:合同的审核历史(分页)

权限设计(与 contract_service / analysis_service 一致):
- admin / contract_manager:可审核 / 查询任意合同
- employee:仅可查询 creator_id == 自己 的合同(触发审核由 API 层 @role_required 拦截)

调用链:
api/contract/routes.py(POST /contracts/{id}/review, GET /contracts/{id}/reviews)
api/review/routes.py(GET /reviews/{id})
  → review_service
    → models/review_report.py
    → services/analysis_service.get_contract_fields(只读复用,读字段)
    → models/document.py(只读,取全文)
    → ai/agent/contract_review_agent(ReAct 循环)
      → ai/agent/tools/*(字段查询 / RAG 检索 / 规则检查)

约束:
- 本层不直接渲染模板、不访问 request 对象
- Agent 同步执行(Sprint 5 不引入 Celery)
- Agent 失败(LLM 不可用等)≠ 接口失败:ReviewReport 标记 failed 但仍落库
- 禁止 print() / return str(e)
- 不修改 Sprint 3 Pipeline / Sprint 4 Knowledge Layer 核心逻辑
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.contract import Contract
from app.models.document import Document
from app.models.review_report import ReviewReport
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.services import analysis_service


# ---------- 配置常量 ----------
# Agent 最大 ReAct 迭代次数(v0.7.1: 从 config 读取,默认 5)
# 在 trigger_review 中通过 current_app.config 动态读取,此处仅作注释
# _AGENT_MAX_ITERATIONS 由 config.MAX_AGENT_ITERATIONS 控制(默认 5)

# 全文截断长度(喂给 risk_rule_tool 的 document_text,防止超大文本拖慢检查)
_MAX_DOCUMENT_TEXT_LENGTH = 20000


def _generate_review_no():
    """
    生成审核编号:RV-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突;与 contract_no / task_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'RV-{timestamp}-{suffix}'


def _check_contract_permission(contract, current_user):
    """
    权限校验:employee 仅可操作自己的合同
    (admin / contract_manager 无限制;触发审核由 API 层 @role_required 拦截 employee)

    复用 analysis_service._check_contract_permission 同模式:
    employee 他人合同返回 404(防 ID 枚举,不泄露存在性)
    """
    if current_user and current_user.get('role') == 'employee' \
            and contract.creator_id != current_user['id']:
        raise NotFoundError('合同不存在')


def _load_contract_full_text(contract):
    """
    读取合同全文(Document.text_content,供 risk_rule_tool 关键条款检查)

    策略:
    - 取合同关联的第一个 Document(Sprint 3 为 1:1)
    - text_content 可能为 None(未分析 / 提取失败的合同)
    - 截断超长文本,防止拖慢规则检查

    :param contract: Contract 模型实例
    :return: (text, document_id) 全文文本(可能为 '') + document id(可能为 None)
    """
    document = contract.documents.first() if hasattr(contract, 'documents') else None
    if not document:
        return '', None

    text = document.text_content or ''
    if len(text) > _MAX_DOCUMENT_TEXT_LENGTH:
        text = text[:_MAX_DOCUMENT_TEXT_LENGTH]
        logger.info('[Review] 合同全文截断: contract_id=%s orig_len=%s trunc=%s',
                    contract.id, document.text_length, _MAX_DOCUMENT_TEXT_LENGTH)
    return text, document.id


def trigger_review(contract_id, current_user):
    """
    触发合同 AI 风险审核

    流程:
    1. 校验合同存在 + 权限
    2. 前置校验:合同需已完成 AI 分析(analysis_status=completed),否则提示"请先完成 AI 分析"
       - 说明:无字段则 risk_rule_tool 无依据,Agent 决策质量差;但仍允许降级(有 legacy_json)
       - 严格策略:analysis_status ∈ {completed} 才允许审核;failed/pending/processing 拒绝
    3. 读取合同字段(analysis_service.get_contract_fields,只读复用)
    4. 读取合同全文(Document.text_content)
    5. 创建 ReviewReport(pending)
    6. 同步执行 Contract Review Agent(ReAct 循环)
    7. 落库 risks / risk_level / summary / tool_calls_log / iterations
    8. 提交事务

    :param contract_id: 合同 ID
    :param current_user: {'id','role','username'}
    :return: dict 审核报告信息(含 risks / tool_calls_log)
    """
    # ---------- 1. 校验 ----------
    try:
        cid = int(contract_id)
    except (TypeError, ValueError):
        raise ValidationError('合同 ID 非法')

    contract = db.session.get(Contract, cid)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    # ---------- 2. 前置校验:合同需已完成 AI 分析 ----------
    # analysis_status:pending / processing / completed / failed
    # 仅 completed 允许审核(有 contract_fields 或 legacy_json 可读)
    if contract.analysis_status != 'completed':
        raise BusinessError(
            f'合同尚未完成 AI 分析(当前状态:{contract.analysis_status}),请先完成 AI 分析后再审核'
        )

    # ---------- 3. 读取合同字段(只读复用 analysis_service) ----------
    # current_user=None:Agent 运行时权限已在 service 层校验;
    # analysis_service._check_contract_permission 仅对 employee 生效,None 时跳过
    fields_result = analysis_service.get_contract_fields(cid, current_user=None)
    fields = fields_result.get('fields', [])
    task_info = fields_result.get('task')  # {id, task_no, status} 或 None
    task_id = task_info.get('id') if task_info else None

    logger.info('[Review] 读取字段: contract_id=%s source=%s field_count=%s task_id=%s',
                cid, fields_result.get('source'), len(fields), task_id)

    # ---------- 4. 读取合同全文 ----------
    document_text, document_id = _load_contract_full_text(contract)
    logger.info('[Review] 读取全文: contract_id=%s doc_id=%s text_len=%s',
                cid, document_id, len(document_text))

    # ---------- 5. 创建 ReviewReport(pending) ----------
    review = ReviewReport(
        review_no=_generate_review_no(),
        contract_id=contract.id,
        task_id=task_id,
        status='pending',
        risk_level=None,
        summary=None,
        risks=None,
        tool_calls_log=None,
        iterations=0,
        llm_error=None,
        error_message=None,
        triggered_by=current_user['id'],
        started_time=None,
        finished_time=None,
    )
    db.session.add(review)
    db.session.flush()  # 拿到 review.id

    logger.info('[Review] 审核任务创建: review_no=%s contract_id=%s triggered_by=%s',
                review.review_no, contract.id, current_user.get('username'))

    # ---------- 6. 同步执行 Contract Review Agent ----------
    # 局部 import(避免模块加载时强依赖 agent 层)
    from flask import current_app
    from app.ai.agent import ContractReviewAgent, AgentContext

    # v0.7.1: 从 config 读取最大迭代次数(默认 5)
    max_iterations = current_app.config.get('MAX_AGENT_ITERATIONS', 5)

    ctx = AgentContext(
        contract_id=contract.id,
        contract=contract.to_dict(include_analysis=False),
        fields=fields,
        document_text=document_text,
        task_id=task_id,
        max_iterations=max_iterations,
    )

    # Task 状态推进:pending → running
    review.status = 'running'
    review.started_time = datetime.utcnow()
    db.session.flush()

    try:
        agent = ContractReviewAgent(max_iterations=max_iterations)
        # Sprint 8:重置 llm_client 上下文 token 累计,避免历史残留
        try:
            from app.ai.agent.llm_client import reset_run_usage
            reset_run_usage()
        except Exception:
            pass
        result = agent.run(ctx)
    except Exception as e:
        # Agent 内部异常兜底(正常情况下 Agent 自身有 try/except,不会抛出)
        logger.exception('[Review] Agent 执行异常: review_no=%s', review.review_no)
        review.status = 'failed'
        review.error_message = f'Agent 执行异常: {e}'
        review.finished_time = datetime.utcnow()
        result = None

    # ---------- 7. 落库 Agent 结果 ----------
    if result is not None:
        review.status = result.status  # success / failed
        review.risk_level = result.risk_level if result.is_success else None
        review.summary = result.summary if result.is_success else None
        review.risks = result.risks if result.is_success else None
        review.tool_calls_log = result.tool_calls_log
        # v0.7.1: 落库 Agent Trace + Trace 汇总 + LLM 错误分类
        review.agent_trace = result.agent_trace
        review.trace_summary = result.trace_summary
        review.iterations = result.iterations
        review.llm_error = result.llm_error
        review.llm_error_type = result.llm_error_type
        review.error_message = result.error if result.is_failed else None
        review.finished_time = datetime.utcnow()

    # ---------- 8. 提交事务 ----------
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('[Review] 审核任务提交失败: review_no=%s', review.review_no)
        raise BusinessError('审核任务提交失败,请重试')

    # ---------- Sprint 8: AIRequestLog 落库钩子(失败不影响主业务)----------
    duration_ms = 0
    if review.started_time and review.finished_time:
        duration_ms = int((review.finished_time - review.started_time).total_seconds() * 1000)
    try:
        from app.ai.agent.llm_client import get_run_usage
        from app.services import ai_log_service
        from flask import current_app
        # token:优先 trace_summary.llm_stats,缺失则从 contextvars 兜底
        run_usage = get_run_usage()
        ai_log_service.log_agent_run(
            user_id=current_user.get('id'),
            agent_type='contract_review',
            model=current_app.config.get('DEEPSEEK_MODEL'),
            prompt_version='contract_review_v1',
            agent_result=result,
            related_id=review.id,
            related_type='review',
            latency_ms=duration_ms,
            trace_summary=result.trace_summary if hasattr(result, 'trace_summary') else None,
            extra_tokens=run_usage,
        )
    except Exception as _e:
        logger.warning('[Review] AIRequestLog 记录失败(不影响业务): review_id=%s err=%s', review.id, _e)

    # ---------- Sprint 8: 审核结果缓存(重复合同ID+状态命中可跳过)----------
    try:
        from app import services as _svc_mod
        cs = _svc_mod.cache_service
        cache_key = cs.build_key('review', contract_id, 'latest')
        cs.set(cache_key, review.to_dict(include_risks=True, include_log=True, include_trace=True),
               ttl_seconds=current_app.config.get('CACHE_TTL_REVIEW', 300))
    except Exception as _e:
        logger.warning('[Review] 结果缓存写入失败: review_id=%s err=%s', review.id, _e)

    duration = 0
    if review.started_time and review.finished_time:
        duration = (review.finished_time - review.started_time).total_seconds()
    # v0.7.1: 日志增加 trace_steps / llm_error_type
    trace_steps = len(review.agent_trace) if review.agent_trace else 0
    logger.info('[Review] 审核任务完成: review_no=%s status=%s risk=%s risks=%s '
                'iterations=%s trace_steps=%s llm_error_type=%s duration=%ss',
                review.review_no, review.status, review.risk_level,
                len(review.risks) if review.risks else 0, review.iterations,
                trace_steps, review.llm_error_type, round(duration, 2))

    return review.to_dict(include_risks=True, include_log=True, include_trace=True)


def get_review(review_id, current_user):
    """
    查询审核报告(含 risks 详情 + agent_trace)

    权限:通过 contract_id 关联校验(employee 仅可查自己合同的审核)

    :param review_id: 审核 ID
    :param current_user: {'id','role'}
    :return: dict 审核报告信息(含 risks / tool_calls_log / agent_trace / trace_summary)
    """
    try:
        rid = int(review_id)
    except (TypeError, ValueError):
        raise ValidationError('审核 ID 非法')

    review = db.session.get(ReviewReport, rid)
    if not review:
        raise NotFoundError('审核报告不存在')

    # 通过 contract 校验权限(employee 他人合同审核返回 404 防枚举)
    contract = db.session.get(Contract, review.contract_id)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    return review.to_dict(include_risks=True, include_log=True, include_trace=True)


def get_trace(review_id, current_user):
    """
    查询审核报告 Agent Trace(v0.7.1 新增)

    供前端 Timeline 展示 Agent 执行过程。

    权限:通过 contract_id 关联校验(employee 仅可查自己合同的审核)

    :param review_id: 审核 ID
    :param current_user: {'id','role'}
    :return: dict {
        review_no, status, risk_level, iterations,
        agent_trace: [...],           # 每步 thought/decision/action/observation/duration/status
        trace_summary: {...},         # steps/总耗时/LLM耗时/Tool耗时/Tool统计/LLM统计
        llm_error, llm_error_type,
        started_time, finished_time
    }
    """
    try:
        rid = int(review_id)
    except (TypeError, ValueError):
        raise ValidationError('审核 ID 非法')

    review = db.session.get(ReviewReport, rid)
    if not review:
        raise NotFoundError('审核报告不存在')

    # 通过 contract 校验权限(employee 他人合同审核返回 404 防枚举)
    contract = db.session.get(Contract, review.contract_id)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    return {
        'id': review.id,
        'review_no': review.review_no,
        'contract_id': review.contract_id,
        'status': review.status,
        'risk_level': review.risk_level,
        'iterations': review.iterations,
        'agent_trace': review.agent_trace or [],
        'trace_summary': review.trace_summary or {},
        'llm_error': review.llm_error,
        'llm_error_type': review.llm_error_type,
        'started_time': review.started_time.strftime('%Y-%m-%d %H:%M:%S') if review.started_time else None,
        'finished_time': review.finished_time.strftime('%Y-%m-%d %H:%M:%S') if review.finished_time else None,
    }


def list_contract_reviews(contract_id, current_user, page=1, size=20):
    """
    合同的审核历史(分页)

    权限:
    - admin / contract_manager:可见任意合同审核历史
    - employee:仅可见自己合同的审核历史(他人合同返回 404)

    :param contract_id: 合同 ID
    :param current_user: {'id','role'}
    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :return: dict {items, total, page, size}
        - items: 审核列表(不含 risks 详情,仅摘要信息)
    """
    # ---------- 参数规范化 ----------
    try:
        cid = int(contract_id)
    except (TypeError, ValueError):
        raise ValidationError('合同 ID 非法')

    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(100, int(size)))
    except (TypeError, ValueError):
        size = 20

    # ---------- 校验合同存在 + 权限 ----------
    contract = db.session.get(Contract, cid)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    # ---------- 查询构建 ----------
    query = (
        ReviewReport.query
        .filter_by(contract_id=cid)
        .order_by(ReviewReport.created_time.desc())
    )

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    # 列表场景不返回 risks 详情与 tool_calls_log(减少 payload)
    items = [r.to_dict(include_risks=False, include_log=False) for r in pagination.items]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def list_reviews(current_user, page=1, size=20, risk_level=None, status=None):
    """
    全局审核报告列表(分页,供"合同审核"菜单页)

    权限:
    - admin / contract_manager:可见全部审核
    - employee:仅可见自己合同的审核(通过 contract.creator_id 过滤)

    :param current_user: {'id','role'}
    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param risk_level: 风险等级过滤(high/medium/low/none,可选)
    :param status: 状态过滤(pending/running/success/failed,可选)
    :return: dict {items, total, page, size}
        - items: 审核列表(含关联合同摘要,不含 risks 详情)
    """
    # ---------- 参数规范化 ----------
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(100, int(size)))
    except (TypeError, ValueError):
        size = 20

    # 枚举校验
    if risk_level and risk_level not in ReviewReport.VALID_RISK_LEVELS:
        raise ValidationError(
            f'风险等级非法,允许: {", ".join(ReviewReport.VALID_RISK_LEVELS)}')
    if status and status not in ReviewReport.VALID_STATUSES:
        raise ValidationError(
            f'审核状态非法,允许: {", ".join(ReviewReport.VALID_STATUSES)}')

    # ---------- 查询构建 ----------
    # joinedload 预加载 contract,避免 to_dict(include_contract=True) 时 N+1
    query = ReviewReport.query.options(joinedload(ReviewReport.contract))

    # 权限过滤:employee 仅可见自己合同的审核
    if current_user and current_user.get('role') == 'employee':
        query = query.join(Contract, ReviewReport.contract_id == Contract.id) \
                     .filter(Contract.creator_id == current_user['id'])

    # 风险等级过滤
    if risk_level:
        query = query.filter_by(risk_level=risk_level)

    # 状态过滤
    if status:
        query = query.filter_by(status=status)

    # 排序:created_time DESC
    query = query.order_by(ReviewReport.created_time.desc())

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    # 列表场景:含合同摘要,不含 risks 详情与 tool_calls_log
    items = [
        r.to_dict(include_risks=False, include_log=False, include_contract=True)
        for r in pagination.items
    ]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }
