"""
投标生成业务服务(Sprint 7.1 - v0.9.1 增强)

职责(增强):
- generate_proposal:
  1. 前置守卫 v0.9.1:BidRequirement.status=approved(Bid Agent 只读 approved)
  2. Requirement Context Builder(复用 Sprint 4 Retriever):
     基于 requirement_data 的技术要求/资质/项目名自动检索知识库构建 Context
  3. 同步执行 Proposal Agent → 渲染 Word → 单事务落库
  4. Bid References:每章节落库 document_id + similarity_score 冗余列 + references JSON
  5. Tool Statistics & Trace Summary:统一可观测输出(与 Sprint 5 一致格式)
- get_proposal / get_proposal_trace / list_proposals / get_proposal_file_path
  (返回中含 tool_stats / trace_summary 统一格式)

调用链(复用,不新增层级):
api/bid/routes.py → proposal_service → models → ProposalAgent → Tools
                                              ↑
                                      RequirementContextBuilder
                                              ↑
                                   Sprint 4 KnowledgeRetriever(复用)

Sprint 7.1 变更点:
1. Requirement Review 守卫:仅允许 status=approved 生成(旧数据已迁移回填为 approved)
2. Context Builder 复用 Sprint 4 RAG(不新增第二套知识库)
3. ProposalSection 统一引用格式落库(Bid References:document_id/chunk_id/page_number/similarity_score)
4. Tool Stats 汇总(tool_call_count/success_count/tool_duration_ms/llm_duration_ms/total_duration_ms)
"""
import os
import uuid
from datetime import datetime
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.bid_document import BidDocument
from app.models.bid_requirement import BidRequirement
from app.models.generated_proposal import GeneratedProposal
from app.models.proposal_section import ProposalSection
from app.models.knowledge_document import KnowledgeDocument
from app.utils.exceptions import (
    ValidationError, BusinessError, NotFoundError,
)
from app.utils.file_utils import cleanup_generated_file


# ---------- 配置常量 ----------
# 企业资料拼接长度上限(避免超长 brief 拖慢 LLM)
_MAX_COMPANY_BRIEF_LENGTH = 2000
# 资质 / 业绩清单展示上限
_MAX_QUALIFICATIONS = 20
_MAX_PAST_PROJECTS = 20


def _generate_proposal_no():
    """
    生成编号:PR-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,与 generation_no / review_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'PR-{timestamp}-{suffix}'


def _check_bid_permission(bid_document: BidDocument, current_user):
    """
    权限校验:employee 仅可操作自己上传的招标文件
    (admin / contract_manager 无限制;他人文件返回 404 防枚举)
    """
    if current_user and current_user.get('role') == 'employee' \
            and bid_document.uploader_id != current_user['id']:
        raise NotFoundError('招标文件不存在')


# ============================================================
# 加载企业资料(供 ProposalContext)
# ============================================================
def _load_company_profile():
    """
    从知识库加载企业资料(knowledge_type='company')

    策略:
    - 查询所有 knowledge_type='company' 且 status='active' 的 KnowledgeDocument
    - 拼接 text_content 作为 brief
    - 资质 / 业绩从文本中按关键词抽取(简单规则;复杂抽取由 LLM 在 prompt 中完成)
    - 返回结构(供 CompanyProfileTool 与 ProposalContext)

    :return: dict {
        available: bool,
        company_name: str,           # 从第一个文档标题推断
        brief: str,                  # 拼接的前 N 字
        qualifications: [str],       # 资质清单(从标题抽取)
        past_projects: [str],        # 业绩清单(从标题抽取)
        source_documents: [{id, doc_no, title}],
        source_count: int
    }
    """
    docs = (
        KnowledgeDocument.query
        .filter_by(knowledge_type='company', status='active')
        .order_by(KnowledgeDocument.created_time.desc())
        .all()
    )

    if not docs:
        return {
            'available': False,
            'company_name': '',
            'brief': '',
            'qualifications': [],
            'past_projects': [],
            'source_documents': [],
            'source_count': 0,
        }

    # 拼接 brief(按时间倒序,取前 N 字)
    text_parts = []
    for d in docs:
        if d.text_content:
            text_parts.append(d.text_content)
    brief = '\n\n'.join(text_parts)
    if len(brief) > _MAX_COMPANY_BRIEF_LENGTH:
        brief = brief[:_MAX_COMPANY_BRIEF_LENGTH] + '...(截断)'

    # 简单规则:从文档标题推断资质 / 业绩
    # (复杂抽取由 LLM 在 prompt 中完成;此处仅给 LLM 一个 hint)
    qualifications = []
    past_projects = []
    for d in docs:
        title = (d.title or '').strip()
        if not title:
            continue
        # 标题含"资质" / "证书" / "ISO" → 资质清单
        if any(kw in title for kw in ('资质', '证书', 'ISO', '许可', '认证')):
            qualifications.append(title)
        # 标题含"业绩" / "项目" / "案例" → 业绩清单
        elif any(kw in title for kw in ('业绩', '项目', '案例', '合同')):
            past_projects.append(title)
        # 否则归到 brief 来源(不进清单)

    qualifications = qualifications[:_MAX_QUALIFICATIONS]
    past_projects = past_projects[:_MAX_PAST_PROJECTS]

    # 公司名:从第一个文档的标题推断(去掉扩展名与常见后缀)
    company_name = ''
    if docs:
        first_title = (docs[0].title or '').strip()
        # 简单清理:去扩展名
        if '.' in first_title:
            first_title = first_title.rsplit('.', 1)[0]
        company_name = first_title[:128]

    return {
        'available': True,
        'company_name': company_name,
        'brief': brief,
        'qualifications': qualifications,
        'past_projects': past_projects,
        'source_documents': [
            {'id': d.id, 'doc_no': d.doc_no, 'title': d.title}
            for d in docs
        ],
        'source_count': len(docs),
    }


# ============================================================
# 正式生成投标文件
# ============================================================
def generate_proposal(bid_document_id, current_user, input_data=None):
    """
    正式生成投标文件(完整 Pipeline)

    流程(单事务,沿用 Sprint 6.2 Transaction Hotfix 模式):
    1. 加载并校验招标文件(需 parse_status=success)
    2. 加载招标需求(requirement_data)
    3. 加载企业资料(knowledge_type='company')
    4. 同步执行 Proposal Agent(ReAct 循环,无 DB 写入)
    5. 渲染 Word 文件(事务外,文件系统操作)
    6. 单一事务:
       a. 创建 GeneratedProposal(success,含 trace / sections) + flush
       b. 创建 ProposalSection(每章节一行) + flush
       c. db.session.commit()  ← 唯一 commit
    7. 事务失败 → rollback + 清理 Word 文件

    容错策略:
    - Agent 失败(LLM 不可用)→ 走兜底(无 AI 章节),仍渲染 Word + 落库
    - Agent 异常(代码错误)→ 不创建任何 DB 记录,直接抛出
    - Word 渲染失败 → 不创建任何 DB 记录,直接抛出
    - 事务提交失败 → rollback + 清理 Word 文件

    权限:
    - admin / contract_manager:可基于任意招标文件生成
    - employee:仅可基于自己上传的招标文件生成

    :param bid_document_id: 招标文件 ID
    :param current_user: {'id','role','username'}
    :param input_data: 输入参数(company_profile_overrides / options,可选)
    :return: dict {proposal}
    """
    transaction_id = uuid.uuid4().hex[:8]
    start_ts = datetime.utcnow()

    # ---------- 1. 加载招标文件 ----------
    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')

    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')
    _check_bid_permission(bid_document, current_user)

    # 前置校验:招标文件需已成功解析
    if bid_document.parse_status != 'success':
        raise BusinessError(
            f'招标文件未解析成功(当前状态:{bid_document.parse_status}),请先解析招标文件'
        )

    requirement = bid_document.requirement
    if not requirement:
        raise BusinessError('招标需求未生成,请先重新解析招标文件')

    # ---- Sprint 7.1 Requirement Review 守卫:Bid Agent 只读 approved ----
    # 旧版 success 状态已在迁移脚本中回填为 approved;此处严格校验白名单
    if requirement.status not in BidRequirement.AGENT_READABLE_STATUSES:
        readable = ', '.join(BidRequirement.AGENT_READABLE_STATUSES)
        raise BusinessError(
            f'招标需求状态为 {requirement.status},Bid Agent 仅允许读取状态: {readable}'
            f'(请先将需求审核通过)'
        )

    logger.info('[Prop:generate] [TX:%s] 开始生成: bid_no=%s req=%s@%s fields=%s/%s user=%s',
                transaction_id, bid_document.bid_no,
                requirement.status, requirement.version,
                requirement.field_count, 15 - requirement.field_count,
                current_user.get('username'))

    # ---------- 2. 加载需求 + 企业资料 + Sprint 7.1 Context Builder ----------
    requirements_data = requirement.requirement_data or {}
    company_profile = _load_company_profile()

    logger.info('[Prop:generate] [TX:%s] 企业资料加载: available=%s sources=%s',
                transaction_id, company_profile.get('available'),
                company_profile.get('source_count'))

    # ---- Sprint 7.1 Requirement Context Builder(复用 Sprint 4 Retriever) ----
    rag_context = _build_requirement_rag_context(requirements_data, company_profile)
    logger.info('[Prop:generate] [TX:%s] Context Builder 完成: slots=%s docs=%s duration=%sms',
                transaction_id,
                rag_context.get('stats', {}).get('slots_filled', 0),
                rag_context.get('stats', {}).get('retrieved_count', 0),
                rag_context.get('stats', {}).get('duration_ms', 0))

    # ---------- 3. 同步执行 Proposal Agent(事务外) ----------
    from app.ai.bid import ProposalAgent, ProposalContext

    max_iterations = 5
    try:
        from flask import current_app as _app
        max_iterations = _app.config.get('MAX_AGENT_ITERATIONS', 5)
    except RuntimeError:
        pass  # 非 Flask 上下文兜底(理论上不会触发)

    ctx = ProposalContext(
        bid_info=bid_document.to_dict(include_text=False, include_requirement=False),
        requirements=requirements_data,
        company_profile=company_profile,
        input_data=input_data or {},
        max_iterations=max_iterations,
    )
    # ---- Sprint 7.1 注入 RAG Context(预构建)到 ProposalContext ----
    ctx.rag_context = rag_context

    agent_start = datetime.utcnow()
    try:
        agent = ProposalAgent(max_iterations=max_iterations)
        # Sprint 8:重置 llm_client contextvar token 累计,避免历史残留
        try:
            from app.ai.agent.llm_client import reset_run_usage
            reset_run_usage()
        except Exception:
            pass
        agent_result = agent.run(ctx)
    except Exception as e:
        agent_duration = (datetime.utcnow() - agent_start).total_seconds()
        logger.exception('[Prop:generate] [TX:%s] Agent 执行异常(无 DB 记录,直接返回错误) '
                         'duration=%ss: %s',
                         transaction_id, round(agent_duration, 2), e)
        # Agent 异常 → 不创建任何 DB 记录,直接抛出
        raise BusinessError(f'Agent 执行异常: {e}')

    # 兜底:Agent 失败时仍返回 success(可渲染无 AI 章节的骨架)
    if agent_result is None:
        from app.ai.bid.result import ProposalResult
        agent_result = ProposalResult(
            status=ProposalResult.FAILED,
            generated_sections=[],
            rag_references=[],
            validation_results={'passed': False, 'issues': []},
            summary='Agent 执行异常',
            iterations=0,
            error='Agent 执行异常',
        )

    # ---------- 4. 渲染 Word 文档(事务外,文件系统操作) ----------
    from app.ai.bid import render_proposal

    # 输出标题(用于文件名)
    project_name = requirements_data.get('project_name') or bid_document.title
    output_title = f'{project_name}-投标文件-{datetime.utcnow().strftime("%Y%m%d")}'

    generated_file_path = None  # 跟踪生成的文件路径(供事务回滚清理)
    try:
        render_result = render_proposal(
            bid_info=bid_document.to_dict(include_text=False, include_requirement=False),
            requirements=requirements_data,
            company_profile=company_profile,
            generated_sections=agent_result.generated_sections,
            output_title=output_title,
        )
        generated_file_path = render_result['file_path']
    except Exception as e:
        logger.exception('[Prop:generate] [TX:%s] Word 渲染失败(无 DB 记录,直接返回错误): %s',
                         transaction_id, e)
        # Word 渲染失败 → 不创建任何 DB 记录,直接抛出
        # (render_proposal 内部已自行清理临时文件)
        raise BusinessError(f'Word 渲染失败: {e}')

    file_path = render_result['file_path']
    file_name = render_result['file_name']
    file_size = render_result['file_size']

    # ---------- 5. 单一事务:GeneratedProposal + ProposalSections ----------
    logger.info('[Prop:generate] [TX:%s] 事务开始: file=%s sections=%s',
                transaction_id, file_name, len(agent_result.generated_sections))

    try:
        # 5a. 创建 GeneratedProposal(success,含全部 Agent 结果)
        proposal = GeneratedProposal(
            proposal_no=_generate_proposal_no(),
            bid_document_id=bid_document.id,
            status='success',
            input_data=input_data or {},
            generated_sections=agent_result.generated_sections,
            rag_references=agent_result.rag_references,
            validation_results=agent_result.validation_results,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            agent_trace=agent_result.agent_trace,
            trace_summary=agent_result.trace_summary,
            iterations=agent_result.iterations,
            llm_error=agent_result.llm_error,
            llm_error_type=agent_result.llm_error_type,
            error_message=None,
            triggered_by=current_user['id'],
            started_time=agent_start,
            finished_time=datetime.utcnow(),
        )
        db.session.add(proposal)
        db.session.flush()  # 获取 proposal.id

        # 5b. 创建 ProposalSection(每章节一行)
        # 排序顺序固定:technical=1, commercial=2, responsive=3, qualification=4, summary=5
        section_order = ProposalSection.DEFAULT_SORT_ORDER
        for section in agent_result.generated_sections:
            section_type = section.get('section_type', '')
            section_name = section.get('section_name', '')
            content = section.get('content', '')
            source = section.get('source', 'ai')
            references = section.get('references') or []

            # ---- Sprint 7.1 Bid References:章节级统一引用格式落库 ----
            # 1. 从 references JSON 取 TOP 1 引用填充冗余列 document_id/similarity_score
            top_ref = references[0] if references else {}
            # 兼容 document_id 为 int 或 str
            raw_doc_id = top_ref.get('document_id')
            doc_id = None
            if raw_doc_id is not None and raw_doc_id != '' and raw_doc_id != 'company_profile_inline':
                try:
                    doc_id = int(raw_doc_id)
                except (TypeError, ValueError):
                    doc_id = None
            sim_score = top_ref.get('score') or top_ref.get('similarity_score')
            if sim_score is not None:
                try:
                    sim_score = float(sim_score)
                except (TypeError, ValueError):
                    sim_score = None

            proposal_section = ProposalSection(
                proposal_id=proposal.id,
                section_type=section_type,
                section_name=section_name,
                content=content,
                source=source,
                references=references,
                # ---- Sprint 7.1 新增:统一引用格式冗余列
                document_id=doc_id,
                similarity_score=sim_score,
                sort_order=section_order.get(section_type, 99),
            )
            db.session.add(proposal_section)

        # 5c. 唯一 commit:GeneratedProposal + ProposalSections 原子提交
        db.session.commit()

    except Exception as e:
        # ---------- 事务失败:rollback + 清理 Word 文件 ----------
        db.session.rollback()
        logger.exception('[Prop:generate] [TX:%s] 事务回滚: 清理 Word 文件 + rollback, '
                         '保证 DB 与文件系统一致: %s',
                         transaction_id, e)

        # 清理已生成的 Word 文件(事务失败 → 文件不能留存)
        if generated_file_path:
            cleanup_generated_file(generated_file_path)

        raise BusinessError(f'投标文件生成失败(事务已回滚,Word 文件已清理): {e}')

    # ---------- 6. 事务成功:记录日志 ----------
    # Sprint 8: AIRequestLog 钩子(失败不影响主业务)
    try:
        from app.ai.agent.llm_client import get_run_usage
        from app.services import ai_log_service
        from flask import current_app
        duration_ms = 0
        if proposal.started_time and proposal.finished_time:
            duration_ms = int((proposal.finished_time - proposal.started_time).total_seconds() * 1000)
        ai_log_service.log_agent_run(
            user_id=current_user.get('id'),
            agent_type='bid',
            model=current_app.config.get('DEEPSEEK_MODEL'),
            prompt_version='bid_proposal_v1',
            agent_result=agent_result,
            related_id=proposal.id,
            related_type='proposal',
            latency_ms=duration_ms,
            trace_summary=getattr(agent_result, 'trace_summary', None),
            extra_tokens=get_run_usage(),
        )
    except Exception as _e:
        logger.warning('[Prop:generate] AIRequestLog 记录失败(不影响业务): proposal_id=%s err=%s', proposal.id, _e)

    duration = (datetime.utcnow() - start_ts).total_seconds()
    logger.info('[Prop:generate] [TX:%s] 事务提交成功: proposal_no=%s status=%s '
                'sections=%s refs=%s iterations=%s trace_steps=%s duration=%ss',
                transaction_id, proposal.proposal_no, proposal.status,
                len(proposal.generated_sections or []),
                len(proposal.rag_references or []),
                proposal.iterations,
                len(proposal.agent_trace or []),
                round(duration, 2))

    return {
        'proposal': proposal.to_dict(
            include_sections=True, include_trace=True, include_bid=True,
        ),
    }


# ============================================================
# 查询接口
# ============================================================
def get_proposal(proposal_id, current_user):
    """
    查询投标生成记录详情(含 sections / trace)

    权限:
    - admin / contract_manager:可见任意生成记录
    - employee:仅可见自己触发的生成记录(他人返回 404 防枚举)

    :param proposal_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: dict 生成记录信息(含 generated_sections / rag_references /
                                validation_results / agent_trace / trace_summary)
    """
    try:
        pid = int(proposal_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    proposal = db.session.get(GeneratedProposal, pid)
    if not proposal:
        raise NotFoundError('生成记录不存在')

    # employee 仅可查自己触发的生成记录
    if current_user and current_user.get('role') == 'employee' \
            and proposal.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    return proposal.to_dict(
        include_sections=True, include_trace=True, include_bid=True,
    )


def get_proposal_trace(proposal_id, current_user):
    """
    查询生成记录 Agent Trace(供前端 Timeline 展示)

    权限:同 get_proposal

    :param proposal_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: dict {
        id, proposal_no, bid_document_id, status, iterations,
        agent_trace: [...],
        trace_summary: {...},
        llm_error, llm_error_type,
        started_time, finished_time
    }
    """
    try:
        pid = int(proposal_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    proposal = db.session.get(GeneratedProposal, pid)
    if not proposal:
        raise NotFoundError('生成记录不存在')

    if current_user and current_user.get('role') == 'employee' \
            and proposal.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    return {
        'id': proposal.id,
        'proposal_no': proposal.proposal_no,
        'bid_document_id': proposal.bid_document_id,
        'status': proposal.status,
        'iterations': proposal.iterations,
        'agent_trace': proposal.agent_trace or [],
        'trace_summary': proposal.trace_summary or {},
        'llm_error': proposal.llm_error,
        'llm_error_type': proposal.llm_error_type,
        'started_time': proposal.started_time.strftime('%Y-%m-%d %H:%M:%S')
                         if proposal.started_time else None,
        'finished_time': proposal.finished_time.strftime('%Y-%m-%d %H:%M:%S')
                         if proposal.finished_time else None,
    }


def list_proposals(current_user, page=1, size=20, status=None,
                   bid_document_id=None):
    """
    生成记录分页列表

    权限:
    - admin / contract_manager:可见全部生成记录
    - employee:仅可见自己触发的生成记录

    :param current_user: {'id','role'}
    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param status: 状态过滤(pending / running / success / failed,可选)
    :param bid_document_id: 招标文件过滤(可选)
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

    if status and status not in GeneratedProposal.VALID_STATUSES:
        raise ValidationError(
            f'生成状态非法,允许: {", ".join(GeneratedProposal.VALID_STATUSES)}'
        )

    # ---------- 查询构建 ----------
    query = GeneratedProposal.query.options(
        joinedload(GeneratedProposal.bid_document),
    )

    # 权限过滤:employee 仅可见自己触发的生成记录
    if current_user and current_user.get('role') == 'employee':
        query = query.filter_by(triggered_by=current_user['id'])

    if status:
        query = query.filter_by(status=status)

    if bid_document_id:
        try:
            bid_id = int(bid_document_id)
            query = query.filter_by(bid_document_id=bid_id)
        except (TypeError, ValueError):
            raise ValidationError('招标文件 ID 非法')

    # 排序:created_time DESC
    query = query.order_by(GeneratedProposal.created_time.desc())

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    # 列表场景:不含 sections / trace,仅摘要 + 招标文件摘要
    items = [
        p.to_dict(include_sections=False, include_trace=False, include_bid=True)
        for p in pagination.items
    ]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def get_proposal_file_path(proposal_id, current_user):
    """
    获取生成文件路径(供 download 接口使用,不暴露给客户端)

    校验:
    - 生成记录存在 + 权限
    - status=success(失败记录无文件)
    - 文件物理存在

    :param proposal_id: 生成记录 ID
    :param current_user: {'id','role'}
    :return: tuple (proposal, file_path, download_name)
    :raises NotFoundError: 记录不存在 / 文件不存在
    :raises BusinessError: 状态不允许下载
    """
    try:
        pid = int(proposal_id)
    except (TypeError, ValueError):
        raise ValidationError('生成记录 ID 非法')

    proposal = db.session.get(GeneratedProposal, pid)
    if not proposal:
        raise NotFoundError('生成记录不存在')

    # 权限校验
    if current_user and current_user.get('role') == 'employee' \
            and proposal.triggered_by != current_user['id']:
        raise NotFoundError('生成记录不存在')

    # 状态校验
    if proposal.status != 'success':
        raise BusinessError(
            f'生成记录状态为 {proposal.status},无法下载(仅成功生成的投标文件可下载)'
        )

    if not proposal.file_path or not os.path.exists(proposal.file_path):
        logger.error('[Prop:download] 生成文件丢失: proposal_id=%s path=%s',
                     proposal.id, proposal.file_path)
        raise NotFoundError('生成文件不存在或已被删除')

    # 下载文件名(用户友好名:项目名 + 投标文件.docx)
    bid_doc = proposal.bid_document
    project_name = ''
    if bid_doc and bid_doc.requirement and bid_doc.requirement.requirement_data:
        project_name = bid_doc.requirement.requirement_data.get('project_name') or ''
    if not project_name and bid_doc:
        project_name = bid_doc.title or ''
    if not project_name:
        project_name = proposal.proposal_no

    download_name = f'{project_name}-投标文件.docx'

    return proposal, proposal.file_path, download_name


# ============================================================
# Sprint 7.1 新增:Requirement Context Builder + Tool Stats
# ============================================================
def _build_requirement_rag_context(requirements_data: dict, company_profile: dict) -> dict:
    """
    Sprint 7.1 新增: Requirement Context Builder
    Bid Agent 不再直接基于 Requirement 生成,先检索企业知识库构建 Context。

    复用 Sprint 4: app.ai.rag.retriever.KnowledgeRetriever
    (不重复实现 RAG,不新增第二套知识库)

    返回结构见:app.ai.bid.context_builder.RequirementContextBuilder.build()
    失败时返回空结构(不影响主流程,Agent 回退到无 Context)
    """
    try:
        from app.ai.bid.context_builder import RequirementContextBuilder
        # Sprint 4 KnowledgeRetriever(单例)
        from app.ai.rag.retriever import get_retriever
        retriever = get_retriever()
        builder = RequirementContextBuilder(retriever)
        return builder.build(requirements_data or {}, company_profile or {})
    except Exception as e:
        logger.warning(
            '[Prop:context_builder] RAG Context 构建失败(已回退:无 Context 继续执行): %s',
            e
        )
        return {
            'technical': [],
            'qualification': [],
            'case': [],
            'company': [],
            'query_terms': {
                'technical': [], 'qualification': [], 'case': [], 'company': [],
            },
            'stats': {
                'retrieved_count': 0,
                'slots_filled': 0,
                'duration_ms': 0,
                'error': str(e),
            },
        }


# ============================================================
# Sprint 7.1 Tool Statistics & Trace 汇总辅助
# (供后续 get_proposal_trace 复用,保持与 Sprint 5 统一格式)
# ============================================================
def aggregate_tool_stats(agent_trace: list, trace_summary: dict,
                         total_duration_s: float) -> dict:
    """
    Sprint 7.1 新增:汇总 Agent Trace 中的 Tool Statistics,与 Sprint 5 统一格式

    输出:
    {
      tool_call_count:    int, // Tool 调用总次数
      tool_success_count:int, // Tool 成功次数(ok=True)
      tool_failed_count: int, // Tool 失败次数
      tool_success_rate: float|null, // 成功率
      tool_duration_ms:  int|null, // Tool 执行耗时
      llm_duration_ms:   int|null, // LLM 总耗时(从 trace_summary 抽)
      total_duration_ms: int,      // 总耗时
      tool_breakdown: [{name, count, success, failed, avg_ms}],
    }
    """
    trace = agent_trace or []
    summary = trace_summary or {}

    tool_steps = [t for t in trace if isinstance(t, dict) and t.get('type') == 'tool']
    tool_call_count = len(tool_steps)

    success_count = 0
    failed_count = 0
    tool_total_ms = 0
    breakdown: dict[str, dict] = {}

    for s in tool_steps:
        name = str(s.get('tool_name') or s.get('name') or 'unknown')
        ok = bool(s.get('success') if 'success' in s
                  else (s.get('error') is None and not s.get('is_error')))
        if ok:
            success_count += 1
        else:
            failed_count += 1
        dur = s.get('duration_ms') or s.get('elapsed_ms') or 0
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            dur = 0
        tool_total_ms += dur

        if name not in breakdown:
            breakdown[name] = {
                'name': name, 'count': 0, 'success': 0, 'failed': 0, 'total_ms': 0,
            }
        breakdown[name]['count'] += 1
        if ok:
            breakdown[name]['success'] += 1
        else:
            breakdown[name]['failed'] += 1
        breakdown[name]['total_ms'] += dur

    breakdown_list = []
    for name, b in breakdown.items():
        avg_ms = (b['total_ms'] // b['count']) if b['count'] > 0 else 0
        breakdown_list.append({
            'name': name,
            'count': b['count'],
            'success': b['success'],
            'failed': b['failed'],
            'avg_ms': avg_ms,
            'total_ms': b['total_ms'],
        })
    breakdown_list.sort(key=lambda x: x['count'], reverse=True)

    # LLM Duration:来自 trace_summary(如果 Agent 已计算)
    llm_ms = summary.get('llm_duration_ms')
    if llm_ms is None:
        llm_guess = int(summary.get('llm_calls', 0)) * 2000  # 经验 2s/call
        llm_ms = llm_guess if summary.get('llm_calls') else None

    success_rate = None
    if tool_call_count > 0:
        success_rate = round(success_count / tool_call_count, 4)

    total_ms = int(max(0, total_duration_s) * 1000)

    return {
        'tool_call_count': tool_call_count,
        'tool_success_count': success_count,
        'tool_failed_count': failed_count,
        'tool_success_rate': success_rate,
        'tool_duration_ms': tool_total_ms if tool_total_ms > 0 else None,
        'llm_duration_ms': llm_ms,
        'total_duration_ms': total_ms,
        'tool_breakdown': breakdown_list,
    }
