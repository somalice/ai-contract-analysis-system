"""
合同生成业务服务(Sprint 6 - v0.8.0)

职责:
- preview_generation:预览生成结果(只跑 Agent,不渲染 Word,不建合同,不落库为 success)
- generate_contract:正式生成(跑 Agent → 渲染 Word → 建合同 → 落库)
- get_generation:查询生成记录(含 clauses / trace)
- get_trace:查询 Agent Trace(供前端 Timeline)
- list_generations:生成记录分页列表
- get_generated_file_path:获取生成文件路径(供 download 接口)

权限设计(与 contract_service / review_service 一致):
- admin / contract_manager:可生成 / 查询任意生成记录
- employee:可生成 / 仅可查询自己触发的生成记录

调用链:
api/generation/routes.py(POST /generation/preview, POST /generation/generate,
                        GET /generation/history, GET /generated/{id}/download)
  → generation_service
    → models/generated_contract.py
    → models/contract_template.py
    → ai/generation/GenerationAgent(ReAct 循环)
      → ai/generation/tools/*(模板查询 / RAG 检索复用 / 条款生成 / 规则校验)
    → ai/generation/word_renderer(渲染 Word)
    → services/contract_service.create_contract_from_generation(建合同)

约束:
- 本层不直接渲染模板、不访问 request 对象
- Agent 同步执行(Sprint 6 不引入 Celery)
- Agent 失败(LLM 不可用)≠ 接口失败:走兜底,仍渲染 Word(无 AI 条款)
- 禁止 print() / return str(e)
- 不修改 Sprint 3 Pipeline / Sprint 4 Knowledge Layer / Sprint 5 Review Agent 核心逻辑
"""
import os
import uuid
from datetime import datetime
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.contract_template import ContractTemplate
from app.models.generated_contract import GeneratedContract
from app.utils.exceptions import (
    ValidationError, BusinessError, NotFoundError,
)
from app.utils.file_utils import cleanup_generated_file
from app.services import contract_service


# ---------- 配置常量 ----------
# Agent 最大 ReAct 迭代次数(从 config 读取,默认 5,与 Sprint 5 一致)


def _generate_generation_no():
    """
    生成编号:GC-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,与 contract_no / review_no / template_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'GC-{timestamp}-{suffix}'


def _load_template_for_generation(template_id, current_user):
    """
    加载模板并校验可用性

    校验:
    - 模板存在
    - 模板状态为 active(employee 仅能用 active 模板;admin/manager 不限,但仍要求 active 才能生成)
    - 模板文件物理存在

    :param template_id: 模板 ID
    :param current_user: {'id','role'}
    :return: ContractTemplate 模型实例
    :raises NotFoundError: 模板不存在
    :raises BusinessError: 模板已停用 / 文件丢失
    """
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise ValidationError('模板 ID 非法')

    template = db.session.get(ContractTemplate, tid)
    if not template:
        raise NotFoundError('模板不存在')

    # 所有角色都只能基于 active 模板生成(避免使用已停用模板产生新合同)
    if template.status != 'active':
        raise BusinessError(
            f'模板"{template.name}"已停用,无法生成合同;请选择启用的模板'
        )

    # 校验文件物理存在(避免模板文件被外部删除后生成失败)
    if not template.file_path or not os.path.exists(template.file_path):
        logger.error('[Gen] 模板文件丢失: template_id=%s path=%s',
                     template.id, template.file_path)
        raise BusinessError('模板文件丢失,请联系管理员')

    return template


def _validate_input_variables(input_variables, template):
    """
    校验用户填写的变量

    策略:
    - 必填项缺失不报错(留给 contract_rule_tool 提示,Agent 决策是否补充)
    - 仅做类型与长度校验,避免恶意超长输入

    :param input_variables: dict
    :param template: ContractTemplate
    :return: dict 清洗后的变量(字符串值)
    """
    if input_variables is None:
        return {}
    if not isinstance(input_variables, dict):
        raise ValidationError('input_variables 必须是 JSON 对象')

    # 限定只接受模板声明的变量(避免注入无关键)
    declared_names = {v.get('name') for v in (template.variables or []) if v.get('name')}

    cleaned = {}
    for k, v in input_variables.items():
        if not isinstance(k, str) or not k:
            continue
        # 仅接受模板声明过的变量名(防注入)
        if declared_names and k not in declared_names:
            continue
        if v is None:
            cleaned[k] = ''
            continue
        # 字符串化 + 长度限制(单值最大 2000 字符)
        sval = str(v)
        if len(sval) > 2000:
            sval = sval[:2000]
        cleaned[k] = sval
    return cleaned


# ============================================================
# 预览(不渲染 Word,不建合同,不落库为 success)
# ============================================================
def preview_generation(template_id, input_variables, current_user,
                       contract_type=None):
    """
    预览合同生成结果

    Sprint 6.2 Transaction Hotfix:
    - Agent 执行在事务外(不涉及 DB 写入)
    - 整个 DB 操作使用单一事务:创建 GeneratedContract → commit
    - 任何异常 → rollback,不留下孤儿记录
    - 事务边界仅在 GenerationService(本函数)

    流程:
    1. 加载并校验模板(只读)
    2. 校验输入变量(只读)
    3. 同步执行 Generation Agent(ReAct 循环,无 DB 写入)
    4. 单一事务:创建 GeneratedContract(status=success/failed) → commit
    5. 返回预览结果

    权限:任意角色均可预览(生成入口不限,正式生成时由 API 层校验)

    :param template_id: 模板 ID
    :param input_variables: 用户填写的变量 {var_name: value}
    :param current_user: {'id','role','username'}
    :param contract_type: 合同类型(可选,默认取模板的 contract_type)
    :return: dict 预览结果 {
        generation: {...GeneratedContract.to_dict, 含 clauses/trace},
    }
    """
    transaction_id = uuid.uuid4().hex[:8]
    start_ts = datetime.utcnow()

    # ---------- 1. 加载模板(只读) ----------
    template = _load_template_for_generation(template_id, current_user)

    # ---------- 2. 校验输入(只读) ----------
    cleaned_vars = _validate_input_variables(input_variables, template)
    final_contract_type = contract_type or template.contract_type or '未分类'

    logger.info('[Gen:preview] [TX:%s] 开始预览: template_id=%s vars=%s type=%s user=%s',
                transaction_id, template.id, len(cleaned_vars), final_contract_type,
                current_user.get('username'))

    # ---------- 3. 同步执行 Generation Agent(事务外,无 DB 写入) ----------
    from flask import current_app
    from app.ai.generation import GenerationAgent, GenerationContext

    max_iterations = current_app.config.get('MAX_AGENT_ITERATIONS', 5)

    ctx = GenerationContext(
        template=template.to_dict(include_variables=True),
        input_variables=cleaned_vars,
        contract_type=final_contract_type,
        max_iterations=max_iterations,
    )

    agent_start = datetime.utcnow()
    try:
        agent = GenerationAgent(max_iterations=max_iterations)
        # Sprint 8:重置 llm_client contextvar token 累计,避免历史残留
        try:
            from app.ai.agent.llm_client import reset_run_usage
            reset_run_usage()
        except Exception:
            pass
        agent_result = agent.run(ctx)
    except Exception as e:
        agent_duration = (datetime.utcnow() - agent_start).total_seconds()
        logger.exception('[Gen:preview] [TX:%s] Agent 执行异常(无 DB 记录,直接返回错误) '
                         'duration=%ss: %s',
                         transaction_id, round(agent_duration, 2), e)
        # Agent 异常 → 不创建任何 DB 记录,直接抛出
        raise BusinessError(f'Agent 执行异常: {e}')

    if agent_result is None:
        agent_result = _make_empty_result()

    # ---------- 4. 单一事务:创建 GeneratedContract → commit ----------
    generation = GeneratedContract(
        generation_no=_generate_generation_no(),
        template_id=template.id,
        contract_id=None,  # 预览不建合同
        status=agent_result.status,  # success / failed
        input_variables=cleaned_vars,
        generated_clauses=agent_result.generated_clauses,
        rag_references=agent_result.rag_references,
        validation_results=agent_result.validation_results,
        agent_trace=agent_result.agent_trace,
        trace_summary=agent_result.trace_summary,
        iterations=agent_result.iterations,
        llm_error=agent_result.llm_error,
        llm_error_type=agent_result.llm_error_type,
        error_message=agent_result.error if agent_result.is_failed else None,
        file_path=None,  # 预览不渲染
        file_name=None,
        file_size=None,
        triggered_by=current_user['id'],
        started_time=agent_start,
        finished_time=datetime.utcnow(),
    )
    db.session.add(generation)

    try:
        logger.info('[Gen:preview] [TX:%s] 事务提交开始: generation_no=%s',
                    transaction_id, generation.generation_no)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Gen:preview] [TX:%s] 事务回滚: generation_no=%s',
                         transaction_id, generation.generation_no)
        raise BusinessError('预览结果提交失败,请重试')

    # ---------- Sprint 8: AIRequestLog 钩子(失败不影响主业务)----------
    try:
        from app.ai.agent.llm_client import get_run_usage
        from app.services import ai_log_service
        from flask import current_app
        duration_ms = 0
        if generation.started_time and generation.finished_time:
            duration_ms = int((generation.finished_time - generation.started_time).total_seconds() * 1000)
        ai_log_service.log_agent_run(
            user_id=current_user.get('id'),
            agent_type='generation',
            model=current_app.config.get('DEEPSEEK_MODEL'),
            prompt_version='contract_generation_v1',
            agent_result=agent_result,
            related_id=generation.id,
            related_type='generation',
            latency_ms=duration_ms,
            trace_summary=getattr(agent_result, 'trace_summary', None),
            extra_tokens=get_run_usage(),
        )
    except Exception as _e:
        logger.warning('[Gen:preview] AIRequestLog 记录失败(不影响业务): gen_id=%s err=%s', generation.id, _e)

    duration = (datetime.utcnow() - start_ts).total_seconds()
    logger.info('[Gen:preview] [TX:%s] 事务提交成功: generation_no=%s status=%s '
                'clauses=%s refs=%s iterations=%s duration=%ss',
                transaction_id, generation.generation_no, generation.status,
                len(generation.generated_clauses or []),
                len(generation.rag_references or []),
                generation.iterations, round(duration, 2))

    return {
        'generation': generation.to_dict(
            include_clauses=True, include_trace=True,
            include_contract=False, include_template=True,
        ),
    }


# ============================================================
# 正式生成(渲染 Word + 建合同)— Sprint 6.2 统一事务
# ============================================================
def generate_contract(template_id, input_variables, current_user,
                      contract_type=None, title=None, description=None):
    """
    正式生成合同(完整 Pipeline)

    Sprint 6.2 Transaction Hotfix:
    - Agent 执行 + Word 渲染在事务外(不涉及 DB 写入)
    - 整个 DB 操作使用单一事务:GeneratedContract + Contract + Trace + Clauses
    - 任何异常 → rollback + 清理 Word 文件,保证 DB 与文件系统一致
    - 事务边界仅在 GenerationService(本函数)
    - contract_service.create_contract_from_generation(auto_commit=False)
      → 不自行 commit,由本函数统一管理事务

    流程:
    1. 加载并校验模板(只读)
    2. 校验输入变量(只读)
    3. 同步执行 Generation Agent(ReAct 循环,无 DB 写入)
    4. 渲染 Word 文档(文件系统操作,记录 file_path 供回滚清理)
    5. 单一事务:
       a. 创建 GeneratedContract(status=success,含 trace/clauses) + flush
       b. 创建 Contract(auto_commit=False) + flush
       c. 关联 generation.contract_id = contract.id
       d. db.session.commit()  ← 唯一 commit
    6. 事务失败 → rollback + cleanup_generated_file(file_path)
    7. 返回生成结果 + 合同信息

    容错策略:
    - Agent 失败(LLM 不可用)→ 走兜底(无 AI 条款),仍渲染 Word + 建合同
    - Agent 异常(代码错误)→ 不创建任何 DB 记录,直接抛出
    - Word 渲染失败 → 不创建任何 DB 记录,直接抛出(Word 已自行清理临时文件)
    - 事务提交失败 → rollback + 清理 Word 文件,保证一致性

    权限:任意角色均可生成(任务书要求"普通用户仅可使用模板",指使用权限)

    :param template_id: 模板 ID
    :param input_variables: 用户填写的变量 {var_name: value}
    :param current_user: {'id','role','username'}
    :param contract_type: 合同类型(可选,默认取模板的 contract_type)
    :param title: 合同标题(可选,默认取模板名 + 时间戳)
    :param description: 描述(可选)
    :return: dict {generation, contract}
    """
    transaction_id = uuid.uuid4().hex[:8]
    start_ts = datetime.utcnow()

    # ---------- 1. 加载模板(只读) ----------
    template = _load_template_for_generation(template_id, current_user)

    # ---------- 2. 校验输入(只读) ----------
    cleaned_vars = _validate_input_variables(input_variables, template)
    final_contract_type = contract_type or template.contract_type or '未分类'

    logger.info('[Gen:generate] [TX:%s] 开始生成: template_id=%s vars=%s type=%s user=%s',
                transaction_id, template.id, len(cleaned_vars), final_contract_type,
                current_user.get('username'))

    # ---------- 3. 同步执行 Generation Agent(事务外,无 DB 写入) ----------
    from flask import current_app
    from app.ai.generation import GenerationAgent, GenerationContext

    max_iterations = current_app.config.get('MAX_AGENT_ITERATIONS', 5)

    ctx = GenerationContext(
        template=template.to_dict(include_variables=True),
        input_variables=cleaned_vars,
        contract_type=final_contract_type,
        max_iterations=max_iterations,
    )

    agent_start = datetime.utcnow()
    try:
        agent = GenerationAgent(max_iterations=max_iterations)
        # Sprint 8:重置 llm_client contextvar token 累计,避免历史残留
        try:
            from app.ai.agent.llm_client import reset_run_usage
            reset_run_usage()
        except Exception:
            pass
        agent_result = agent.run(ctx)
    except Exception as e:
        agent_duration = (datetime.utcnow() - agent_start).total_seconds()
        logger.exception('[Gen:generate] [TX:%s] Agent 执行异常(无 DB 记录,直接返回错误) '
                         'duration=%ss: %s',
                         transaction_id, round(agent_duration, 2), e)
        # Agent 异常 → 不创建任何 DB 记录,直接抛出
        raise BusinessError(f'Agent 执行异常: {e}')

    # 兜底:Agent 失败时仍返回 success(可渲染无 AI 条款的合同)
    # Agent 内部 _fallback 已经把 status 设为 success
    if agent_result is None:
        agent_result = _make_empty_result()

    # ---------- 4. 渲染 Word 文档(事务外,文件系统操作) ----------
    from app.ai.generation.word_renderer import render_contract

    # 输出标题(用于文件名与合同标题)
    if not title or not title.strip():
        title = f'{template.name}-{datetime.utcnow().strftime("%Y%m%d")}'

    generated_file_path = None  # 跟踪生成的文件路径(供事务回滚清理)
    try:
        render_result = render_contract(
            template_path=template.file_path,
            input_variables=cleaned_vars,
            generated_clauses=agent_result.generated_clauses,
            output_title=title,
        )
        generated_file_path = render_result['file_path']
    except Exception as e:
        logger.exception('[Gen:generate] [TX:%s] Word 渲染失败(无 DB 记录,直接返回错误): %s',
                         transaction_id, e)
        # Word 渲染失败 → 不创建任何 DB 记录,直接抛出
        # (render_contract 内部已自行清理临时文件)
        raise BusinessError(f'Word 渲染失败: {e}')

    file_path = render_result['file_path']
    file_name = render_result['file_name']
    file_size = render_result['file_size']

    # ---------- 5. 单一事务:GeneratedContract + Contract + Trace + Clauses ----------
    logger.info('[Gen:generate] [TX:%s] 事务开始: generation_no待生成 file=%s',
                transaction_id, file_name)

    try:
        # 5a. 创建 GeneratedContract(success,含全部 Agent 结果)
        generation = GeneratedContract(
            generation_no=_generate_generation_no(),
            template_id=template.id,
            contract_id=None,  # 待关联
            status='success',
            input_variables=cleaned_vars,
            generated_clauses=agent_result.generated_clauses,
            rag_references=agent_result.rag_references,
            validation_results=agent_result.validation_results,
            agent_trace=agent_result.agent_trace,
            trace_summary=agent_result.trace_summary,
            iterations=agent_result.iterations,
            llm_error=agent_result.llm_error,
            llm_error_type=agent_result.llm_error_type,
            error_message=None,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            triggered_by=current_user['id'],
            started_time=agent_start,
            finished_time=datetime.utcnow(),
        )
        db.session.add(generation)
        db.session.flush()  # 获取 generation.id,不提交

        # 5b. 创建 Contract(auto_commit=False,不自行 commit)
        contract_dict = contract_service.create_contract_from_generation(
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            current_user=current_user,
            title=title,
            contract_type=final_contract_type,
            description=description,
            auto_commit=False,  # Sprint 6.2:由本函数统一管理事务
        )

        # 5c. 关联 generation.contract_id
        generation.contract_id = contract_dict['id']

        # 5d. 唯一 commit:GeneratedContract + Contract + Trace 原子提交
        db.session.commit()

    except Exception as e:
        # ---------- 事务失败:rollback + 清理 Word 文件 ----------
        db.session.rollback()
        logger.exception('[Gen:generate] [TX:%s] 事务回滚: 清理 Word 文件 + rollback, '
                         '保证 DB 与文件系统一致: %s',
                         transaction_id, e)

        # 清理已生成的 Word 文件(事务失败 → 文件不能留存)
        if generated_file_path:
            cleanup_generated_file(generated_file_path)

        raise BusinessError(f'合同生成失败(事务已回滚,Word 文件已清理): {e}')

    # ---------- 6. 事务成功:记录日志 ----------
    # Sprint 8: AIRequestLog 钩子(失败不影响主业务)
    try:
        from app.ai.agent.llm_client import get_run_usage
        from app.services import ai_log_service
        from flask import current_app
        duration_ms = 0
        if generation.started_time and generation.finished_time:
            duration_ms = int((generation.finished_time - generation.started_time).total_seconds() * 1000)
        ai_log_service.log_agent_run(
            user_id=current_user.get('id'),
            agent_type='generation',
            model=current_app.config.get('DEEPSEEK_MODEL'),
            prompt_version='contract_generation_v1',
            agent_result=agent_result,
            related_id=generation.id,
            related_type='generation',
            latency_ms=duration_ms,
            trace_summary=getattr(agent_result, 'trace_summary', None),
            extra_tokens=get_run_usage(),
        )
    except Exception as _e:
        logger.warning('[Gen:generate] AIRequestLog 记录失败(不影响业务): gen_id=%s err=%s', generation.id, _e)

    duration = (datetime.utcnow() - start_ts).total_seconds()
    logger.info('[Gen:generate] [TX:%s] 事务提交成功: generation_no=%s status=%s '
                'contract_id=%s clauses=%s refs=%s iterations=%s duration=%ss',
                transaction_id, generation.generation_no, generation.status,
                generation.contract_id,
                len(generation.generated_clauses or []),
                len(generation.rag_references or []),
                generation.iterations, round(duration, 2))

    return {
        'generation': generation.to_dict(
            include_clauses=True, include_trace=True,
            include_contract=True, include_template=True,
        ),
        'contract': contract_dict,
    }


def _make_empty_result():
    """构造空结果(Agent 异常时的兜底)"""
    from app.ai.generation.result import GenerationResult
    return GenerationResult(
        status=GenerationResult.FAILED,
        generated_clauses=[],
        rag_references=[],
        validation_results={'passed': False, 'issues': []},
        summary='Agent 执行异常',
        iterations=0,
        error='Agent 执行异常',
    )


# ============================================================
# 查询接口
# ============================================================
def get_generation(generation_id, current_user):
    """
    查询生成记录详情(含 clauses / trace)

    权限:
    - admin / contract_manager:可见任意生成记录
    - employee:仅可见自己触发的生成记录(他人返回 404 防枚举)

    :param generation_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: dict 生成记录信息(含 generated_clauses / rag_references / validation_results /
                                agent_trace / trace_summary)
    """
    try:
        gid = int(generation_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    generation = db.session.get(GeneratedContract, gid)
    if not generation:
        raise NotFoundError('生成记录不存在')

    # employee 仅可查自己触发的生成记录
    if current_user and current_user.get('role') == 'employee' \
            and generation.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    return generation.to_dict(
        include_clauses=True, include_trace=True,
        include_contract=True, include_template=True,
    )


def get_trace(generation_id, current_user):
    """
    查询生成记录 Agent Trace(供前端 Timeline 展示)

    权限:同 get_generation

    :param generation_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: dict {
        id, generation_no, template_id, contract_id, status, iterations,
        agent_trace: [...],
        trace_summary: {...},
        llm_error, llm_error_type,
        started_time, finished_time
    }
    """
    try:
        gid = int(generation_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    generation = db.session.get(GeneratedContract, gid)
    if not generation:
        raise NotFoundError('生成记录不存在')

    if current_user and current_user.get('role') == 'employee' \
            and generation.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    return {
        'id': generation.id,
        'generation_no': generation.generation_no,
        'template_id': generation.template_id,
        'contract_id': generation.contract_id,
        'status': generation.status,
        'iterations': generation.iterations,
        'agent_trace': generation.agent_trace or [],
        'trace_summary': generation.trace_summary or {},
        'llm_error': generation.llm_error,
        'llm_error_type': generation.llm_error_type,
        'started_time': generation.started_time.strftime('%Y-%m-%d %H:%M:%S')
                        if generation.started_time else None,
        'finished_time': generation.finished_time.strftime('%Y-%m-%d %H:%M:%S')
                         if generation.finished_time else None,
    }


def list_generations(current_user, page=1, size=20, status=None,
                     template_id=None):
    """
    生成记录分页列表

    权限:
    - admin / contract_manager:可见全部生成记录
    - employee:仅可见自己触发的生成记录

    :param current_user: {'id','role'}
    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param status: 状态过滤(pending / running / success / failed,可选)
    :param template_id: 模板过滤(可选)
    :return: dict {items, total, page, size}
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

    if status and status not in GeneratedContract.VALID_STATUSES:
        raise ValidationError(
            f'生成状态非法,允许: {", ".join(GeneratedContract.VALID_STATUSES)}')

    # ---------- 查询构建 ----------
    query = GeneratedContract.query.options(
        joinedload(GeneratedContract.template),
        joinedload(GeneratedContract.contract),
    )

    # 权限过滤:employee 仅可见自己触发的生成记录
    if current_user and current_user.get('role') == 'employee':
        query = query.filter_by(triggered_by=current_user['id'])

    if status:
        query = query.filter_by(status=status)

    if template_id:
        try:
            tid = int(template_id)
            query = query.filter_by(template_id=tid)
        except (TypeError, ValueError):
            raise ValidationError('模板 ID 非法')

    # 排序:created_time DESC
    query = query.order_by(GeneratedContract.created_time.desc())

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    # 列表场景:不含 clauses / trace,仅摘要 + 合同摘要
    items = [
        g.to_dict(include_clauses=False, include_trace=False,
                  include_contract=True, include_template=True)
        for g in pagination.items
    ]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def get_generated_file_path(generation_id, current_user):
    """
    获取生成文件路径(供 download 接口使用,不暴露给客户端)

    校验:
    - 生成记录存在 + 权限
    - status=success(预览/失败记录无文件)
    - 文件物理存在

    :param generation_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: tuple (generation, file_path, download_name)
    :raises NotFoundError: 记录不存在 / 文件不存在
    :raises BusinessError: 状态不允许下载
    """
    try:
        gid = int(generation_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    generation = db.session.get(GeneratedContract, gid)
    if not generation:
        raise NotFoundError('生成记录不存在')

    # 权限校验
    if current_user and current_user.get('role') == 'employee' \
            and generation.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    # 状态校验
    if generation.status != 'success':
        raise BusinessError(
            f'生成记录状态为 {generation.status},无法下载(仅成功生成的合同可下载)'
        )

    if not generation.file_path or not os.path.exists(generation.file_path):
        logger.error('[Gen:download] 生成文件丢失: generation_id=%s path=%s',
                     generation.id, generation.file_path)
        raise NotFoundError('生成文件不存在或已被删除')

    # 下载文件名(用户友好名:合同标题 + .docx)
    download_name = f'{generation.contract.title}.docx' if generation.contract \
        else (generation.file_name or f'{generation.generation_no}.docx')

    return generation, generation.file_path, download_name
