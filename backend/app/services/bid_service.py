"""
招标文件业务服务(Sprint 7.1 - v0.9.1 增强)

职责(扩展):
- upload_bid_document:上传 → BidDocument → Bid Pipeline → BidRequirement
  (v0.9.1:成功默认 status=draft,需人工审核 approved 后 Bid Agent 可见;
  version=v1.0;field_sources 一并落库)
- parse_bid_document:重新解析(v0.9.1:重新解析 version 自增,status 重置 draft)
- get_bid_requirement:查询需求(v0.9.1:含 version / field_sources)
- list_bid_documents / get_bid_document_detail:分页 / 详情
- delete_bid_document:删除(admin / contract_manager)
- ---------- v0.9.1 新增 Requirement Review ----------
- submit_requirement_for_review: draft → reviewing
- review_requirement: reviewing → approved(通过) or → draft(驳回)
- update_requirement_status:通用状态校验(按 VALID_TRANSITIONS)

调用链(与 v0.9.0 一致,复用):
api/bid/routes.py → bid_service → models → ai/bid.pipeline → requirement_extractor

Sprint 7.1 增强点:
1. Requirement Version: parse_bid_document 重新解析时 version 自增(v1.0→v1.1)
2. Requirement Review: draft→reviewing→approved / failed(不进入审核流)
3. Requirement Trace: field_sources(4 字段/page_number/chunk_id/confidence/source_text)
4. Proposal Agent 默认只读取 status=approved(由 proposal_service 守卫)
"""
import os
import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.bid_document import BidDocument
from app.models.bid_requirement import BidRequirement
from app.utils.exceptions import (
    ValidationError, BusinessError, NotFoundError,
)


# ---------- 配置常量 ----------
_BID_SUBDIR = 'bids'  # 招标文件子目录(相对 UPLOAD_FOLDER)


def _get_bid_upload_dir():
    """获取招标文件上传目录(uploads/bids/),并确保目录存在。"""
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], _BID_SUBDIR)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _generate_bid_no():
    """
    生成招标编号:BD-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突;与 contract_no / review_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'BD-{timestamp}-{suffix}'


def _generate_requirement_no():
    """
    生成需求编号:BR-YYYYMMDDHHMMSS-XXXXXXXX
    (与 bid_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'BR-{timestamp}-{suffix}'


def _get_file_ext(filename: str) -> str:
    """获取小写扩展名(无点)"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'


def _check_bid_permission(bid_document: BidDocument, current_user):
    """
    权限校验:employee 仅可操作自己上传的招标文件
    (admin / contract_manager 无限制;他人文件返回 404 防枚举,不泄露存在性)
    """
    if current_user and current_user.get('role') == 'employee' \
            and bid_document.uploader_id != current_user['id']:
        raise NotFoundError('招标文件不存在')


def _is_allowed_bid_file(filename: str) -> bool:
    """
    校验是否为允许的招标文件类型
    - 复用 config.ALLOWED_EXTENSIONS(pdf / png / jpg / jpeg 等)
    - 不引入新配置,保持配置统一
    """
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in current_app.config.get('ALLOWED_EXTENSIONS', set())


# ============================================================
# 上传招标文件(落库 + 同步执行 Pipeline)
# ============================================================
def upload_bid_document(file, current_user, title=None):
    """
    上传招标文件 → 落库 BidDocument → 同步执行 Bid Pipeline → 落库 BidRequirement

    流程(单事务):
    1. 校验文件名 / 类型
    2. 保存文件到 uploads/bids/{uuid}.ext
    3. 创建 BidDocument(parse_status=pending) + flush
    4. 调用 run_bid_pipeline(复用 Sprint 3 提取 + Sprint 4 Chunker + Sprint 5 LLM)
    5. 创建 / 更新 BidRequirement(1:1,UPSERT)
    6. 回写 BidDocument(parse_status=success / failed, text_content, extract_method)
    7. commit

    容错:
    - Pipeline 失败(LLM 不可用 / OCR 失败)≠ 接口失败:
      BidDocument 仍落库(parse_status=failed),前端可"重新解析"
    - 文件保存失败 → 抛 BusinessError(无残留文件)
    - DB 失败 → rollback + 清理文件

    :param file: werkzeug FileStorage
    :param current_user: {'id','role','username'}
    :param title: 招标标题(默认取文件名去扩展名)
    :return: dict 招标文件信息(含 requirement 概要)
    """
    # ---------- 1. 校验 ----------
    original_filename = file.filename
    if not original_filename:
        raise ValidationError('文件名为空')
    if not _is_allowed_bid_file(original_filename):
        raise ValidationError(
            f'招标文件类型不支持,允许: {", ".join(sorted(current_app.config.get("ALLOWED_EXTENSIONS", set())))}'
        )

    if title and len(title) > 255:
        raise ValidationError('招标标题长度不能超过 255 字符')

    ext = _get_file_ext(original_filename)

    # ---------- 2. 保存文件 ----------
    bid_dir = _get_bid_upload_dir()
    saved_filename = f'{uuid.uuid4().hex}.{ext}'
    file_path = os.path.join(bid_dir, saved_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception:
        logger.exception('[Bid:upload] 文件保存失败: filename=%s', original_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise BusinessError('文件保存失败,请重试')

    # ---------- 3. 创建 BidDocument(parse_status=pending) ----------
    bid_no = _generate_bid_no()
    if not title or not title.strip():
        title = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

    # 文件类型(pdf / image)
    file_type = 'pdf' if ext == 'pdf' else 'image'

    bid_document = BidDocument(
        bid_no=bid_no,
        title=title.strip(),
        file_name=original_filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
        page_count=0,
        text_content=None,
        text_length=0,
        parse_status='pending',
        extract_method='none',
        error_message=None,
        uploader_id=current_user['id'],
    )
    db.session.add(bid_document)
    db.session.flush()  # 拿到 bid_document.id

    logger.info('[Bid:upload] 招标文件记录创建: bid_no=%s uploader=%s',
                bid_no, current_user.get('username'))

    # ---------- 4. 同步执行 Bid Pipeline ----------
    # Pipeline 失败不抛异常(返回 error dict),由本函数决策 UPDATE 状态
    from app.ai.bid.pipeline import run_bid_pipeline

    pipeline_start = datetime.utcnow()
    try:
        pipeline_result = run_bid_pipeline(file_path, original_filename)
    except Exception as e:
        # Pipeline 内部异常兜底(正常不抛,返回 error)
        logger.exception('[Bid:upload] Pipeline 异常: bid_no=%s', bid_no)
        pipeline_result = {
            'text': '',
            'extract_method': 'none',
            'page_count': 0,
            'requirements': None,
            'error': f'Pipeline 执行异常: {e}',
        }

    pipeline_duration = (datetime.utcnow() - pipeline_start).total_seconds()
    text = pipeline_result.get('text', '') or ''
    extract_method = pipeline_result.get('extract_method', 'none')
    page_count = pipeline_result.get('page_count', 0)
    requirements = pipeline_result.get('requirements')
    pipeline_error = pipeline_result.get('error')

    logger.info('[Bid:upload] Pipeline 完成: bid_no=%s method=%s pages=%s text_len=%s '
                'req_error=%s duration=%ss',
                bid_no, extract_method, page_count, len(text),
                requirements.get('error') if requirements else 'no-requirements',
                round(pipeline_duration, 2))

    # ---------- 5. 创建 / 更新 BidRequirement(1:1) ----------
    # 重新解析时 UPDATE 原行(uselist=False + flush 后查 existing);此处为首次创建
    #
    # [Bugfix] 防御性清理:历史环境中可能存在孤儿 bid_requirements
    # (bid_document 被绕过 ORM 删除 / SQLite foreign_keys 未开启导致未级联),
    # 此时再次创建相同 bid_document_id 的 requirement 会触发
    # UNIQUE constraint failed: bid_requirements.bid_document_id 错误,
    # 前端提示"招标文件保存失败,请重试"。
    # 先 flush 把孤儿 requirement 删除,再正常 add 新的 requirement。
    BidRequirement.query.filter_by(bid_document_id=bid_document.id).delete(
        synchronize_session=False
    )
    db.session.flush()

    requirement = _build_requirement_from_pipeline(
        bid_document.id, requirements, pipeline_error
    )
    if requirement is not None:
        db.session.add(requirement)

    # ---------- 6. 回写 BidDocument ----------
    bid_document.text_content = text if text else None
    bid_document.text_length = len(text)
    bid_document.page_count = page_count
    bid_document.extract_method = extract_method

    if pipeline_error or not text:
        # Pipeline 失败(文本提取失败)
        bid_document.parse_status = 'failed'
        bid_document.error_message = pipeline_error or '招标文件未提取到文本'
    elif requirements and requirements.get('error'):
        # 文本提取成功,但 LLM 解析需求失败
        bid_document.parse_status = 'failed'
        bid_document.error_message = f'需求解析失败: {requirements["error"]}'
    elif requirements and requirements.get('requirement_data'):
        # 全流程成功
        bid_document.parse_status = 'success'
        bid_document.error_message = None
    else:
        # 兜底:不应到达
        bid_document.parse_status = 'failed'
        bid_document.error_message = '需求解析未知失败'

    # ---------- 7. 提交事务 ----------
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # 事务失败:清理已保存文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        logger.exception('[Bid:upload] 事务提交失败: bid_no=%s', bid_no)
        raise BusinessError('招标文件保存失败,请重试')

    logger.info('[Bid:upload] 招标文件上传完成: bid_no=%s status=%s text_len=%s',
                bid_no, bid_document.parse_status, bid_document.text_length)

    return bid_document.to_dict(include_text=False, include_requirement=True)


def _build_requirement_from_pipeline(bid_document_id: int,
                                      requirements: dict,
                                      pipeline_error: str = None,
                                      current_version: str = None) -> BidRequirement:
    """
    从 Pipeline 输出构建 BidRequirement 实例(Sprint 7.1 增强)

    v0.9.1 变更:
    - 成功时 status=draft(不再 'success',需要审核后 Bid Agent 才能读取)
    - version 支持(新建=v1.0,重新解析=next_version)
    - field_sources 落库

    :param bid_document_id: 关联的招标文件 ID
    :param requirements: extract_requirements 返回的 dict(含 field_sources)
    :param pipeline_error: Pipeline 错误
    :param current_version: 当前版本(重新解析时传入,用于自增;None=新建)
    :return: BidRequirement 实例;None 表示不应建记录
    """
    requirement_no = _generate_requirement_no()
    new_version = BidRequirement.next_version(current_version) \
        if current_version else 'v1.0'

    # Pipeline 失败(无 requirements)
    if requirements is None:
        return BidRequirement(
            requirement_no=requirement_no,
            bid_document_id=bid_document_id,
            status='failed',
            version=new_version,
            requirement_data=None,
            field_sources=None,
            project_name=None,
            budget=None,
            deadline=None,
            field_count=0,
            missing_count=15,
            confidence=None,
            error_message=pipeline_error or '招标文件解析失败',
        )

    # requirements 存在但 LLM 失败
    if requirements.get('error'):
        return BidRequirement(
            requirement_no=requirement_no,
            bid_document_id=bid_document_id,
            status='failed',
            version=new_version,
            requirement_data=None,
            field_sources=None,
            project_name=None,
            budget=None,
            deadline=None,
            field_count=requirements.get('field_count', 0),
            missing_count=requirements.get('missing_count', 15),
            confidence=None,
            error_message=requirements['error'],
        )

    # 成功:提取冗余字段(v0.9.1:status=draft,待审核)
    req_data = requirements.get('requirement_data') or {}
    field_sources = requirements.get('field_sources')
    project_name = req_data.get('project_name')
    if isinstance(project_name, str):
        project_name = project_name.strip()[:255] if project_name.strip() else None
    else:
        project_name = None

    budget = req_data.get('budget')
    if isinstance(budget, str):
        budget = budget.strip()[:64] if budget.strip() else None
    else:
        budget = None

    deadline = req_data.get('deadline')
    if isinstance(deadline, str):
        deadline = deadline.strip()[:64] if deadline.strip() else None
    else:
        deadline = None

    return BidRequirement(
        requirement_no=requirement_no,
        bid_document_id=bid_document_id,
        status='draft',   # Sprint 7.1 Requirement Review:解析成功 = 草稿态
        version=new_version,
        requirement_data=req_data,
        field_sources=field_sources,   # Sprint 7.1 Requirement Trace
        project_name=project_name,
        budget=budget,
        deadline=deadline,
        field_count=requirements.get('field_count', 0),
        missing_count=requirements.get('missing_count', 15),
        confidence=requirements.get('confidence'),
        error_message=None,
    )


# ============================================================
# 重新解析招标文件
# ============================================================
def parse_bid_document(bid_document_id, current_user):
    """
    重新解析招标文件

    场景:首次解析失败(LLM 不可用 / OCR 失败)后,LLM 恢复时重试

    流程:
    1. 校验招标文件存在 + 权限
    2. 调用 run_bid_pipeline(复用已落库文件)
    3. UPSERT BidRequirement(1:1,UPDATE 原行;无则 INSERT)
    4. 回写 BidDocument(parse_status / text_content / extract_method)
    5. commit

    权限:
    - admin / contract_manager:可重新解析任意招标文件
    - employee:仅可重新解析自己上传的

    :param bid_document_id: 招标文件 ID
    :param current_user: {'id','role','username'}
    :return: dict 更新后的招标文件信息(含 requirement)
    """
    # ---------- 1. 校验 ----------
    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')

    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')
    _check_bid_permission(bid_document, current_user)

    # 文件物理存在校验
    if not bid_document.file_path or not os.path.exists(bid_document.file_path):
        logger.error('[Bid:parse] 招标文件物理丢失: bid_no=%s path=%s',
                     bid_document.bid_no, bid_document.file_path)
        raise BusinessError('招标文件丢失,无法重新解析')

    logger.info('[Bid:parse] 重新解析开始: bid_no=%s operator=%s',
                bid_document.bid_no, current_user.get('username'))

    # ---------- 2. 执行 Pipeline ----------
    from app.ai.bid.pipeline import run_bid_pipeline

    # 标记为 processing(瞬时状态,正常立即变 success / failed)
    bid_document.parse_status = 'processing'
    bid_document.error_message = None
    db.session.flush()

    pipeline_start = datetime.utcnow()
    try:
        pipeline_result = run_bid_pipeline(
            bid_document.file_path, bid_document.file_name
        )
    except Exception as e:
        logger.exception('[Bid:parse] Pipeline 异常: bid_no=%s', bid_document.bid_no)
        pipeline_result = {
            'text': '',
            'extract_method': 'none',
            'page_count': 0,
            'requirements': None,
            'error': f'Pipeline 执行异常: {e}',
        }

    pipeline_duration = (datetime.utcnow() - pipeline_start).total_seconds()
    text = pipeline_result.get('text', '') or ''
    extract_method = pipeline_result.get('extract_method', 'none')
    page_count = pipeline_result.get('page_count', 0)
    requirements = pipeline_result.get('requirements')
    pipeline_error = pipeline_result.get('error')

    logger.info('[Bid:parse] Pipeline 完成: bid_no=%s method=%s text_len=%s duration=%ss',
                bid_document.bid_no, extract_method, len(text), round(pipeline_duration, 2))

    # ---------- 3. UPSERT BidRequirement ----------
    existing_requirement = bid_document.requirement  # 1:1 backref

    if existing_requirement is None:
        # 首次建(理论上 upload 时已建,兜底)
        requirement = _build_requirement_from_pipeline(
            bid_document.id, requirements, pipeline_error
        )
        if requirement is not None:
            db.session.add(requirement)
    else:
        # UPDATE 原行(uselist=False,1:1 关系,重新解析覆盖)
        _update_requirement_from_pipeline(
            existing_requirement, requirements, pipeline_error,
            # v0.9.1:重新解析 = 新版本号
            current_version=existing_requirement.version,
        )

    # ---------- 4. 回写 BidDocument ----------
    bid_document.text_content = text if text else None
    bid_document.text_length = len(text)
    bid_document.page_count = page_count
    bid_document.extract_method = extract_method

    if pipeline_error or not text:
        bid_document.parse_status = 'failed'
        bid_document.error_message = pipeline_error or '招标文件未提取到文本'
    elif requirements and requirements.get('error'):
        bid_document.parse_status = 'failed'
        bid_document.error_message = f'需求解析失败: {requirements["error"]}'
    elif requirements and requirements.get('requirement_data'):
        bid_document.parse_status = 'success'
        bid_document.error_message = None
    else:
        bid_document.parse_status = 'failed'
        bid_document.error_message = '需求解析未知失败'

    # ---------- 5. 提交事务 ----------
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Bid:parse] 事务提交失败: bid_no=%s', bid_document.bid_no)
        raise BusinessError('重新解析失败,请重试')

    logger.info('[Bid:parse] 重新解析完成: bid_no=%s status=%s',
                bid_document.bid_no, bid_document.parse_status)

    return bid_document.to_dict(include_text=False, include_requirement=True)


def _update_requirement_from_pipeline(requirement: BidRequirement,
                                       requirements: dict,
                                       pipeline_error: str = None,
                                       current_version: str = None):
    """
    用 Pipeline 输出更新已存在的 BidRequirement(Sprint 7.1 增强)

    v0.9.1 变更:
    - 成功 status=draft(重置审核状态,因为内容变了需要重新审核)
    - version=next_version(current_version)
    - field_sources 落库

    :param requirement: 已存在的 BidRequirement 实例
    :param requirements: extract_requirements 返回的 dict
    :param pipeline_error: Pipeline 错误
    :param current_version: 当前版本号(用于自增;None 时用 requirement.version)
    """
    base_version = current_version or requirement.version
    new_version = BidRequirement.next_version(base_version)

    # Pipeline 失败
    if requirements is None:
        requirement.status = 'failed'
        requirement.version = new_version
        requirement.requirement_data = None
        requirement.field_sources = None
        requirement.project_name = None
        requirement.budget = None
        requirement.deadline = None
        requirement.field_count = 0
        requirement.missing_count = 15
        requirement.confidence = None
        requirement.error_message = pipeline_error or '招标文件解析失败'
        return

    # LLM 失败
    if requirements.get('error'):
        requirement.status = 'failed'
        requirement.version = new_version
        requirement.requirement_data = None
        requirement.field_sources = None
        requirement.project_name = None
        requirement.budget = None
        requirement.deadline = None
        requirement.field_count = requirements.get('field_count', 0)
        requirement.missing_count = requirements.get('missing_count', 15)
        requirement.confidence = None
        requirement.error_message = requirements['error']
        return

    # 成功:status=draft(需要重新审核),version++,field_sources 落库
    req_data = requirements.get('requirement_data') or {}
    field_sources = requirements.get('field_sources')
    project_name = req_data.get('project_name')
    if isinstance(project_name, str):
        project_name = project_name.strip()[:255] if project_name.strip() else None
    else:
        project_name = None

    budget = req_data.get('budget')
    if isinstance(budget, str):
        budget = budget.strip()[:64] if budget.strip() else None
    else:
        budget = None

    deadline = req_data.get('deadline')
    if isinstance(deadline, str):
        deadline = deadline.strip()[:64] if deadline.strip() else None
    else:
        deadline = None

    requirement.status = 'draft'   # v0.9.1:重新解析内容,重置到草稿态
    requirement.version = new_version
    requirement.requirement_data = req_data
    requirement.field_sources = field_sources
    requirement.project_name = project_name
    requirement.budget = budget
    requirement.deadline = deadline
    requirement.field_count = requirements.get('field_count', 0)
    requirement.missing_count = requirements.get('missing_count', 15)
    requirement.confidence = requirements.get('confidence')
    requirement.error_message = None


# ============================================================
# Sprint 7.1 新增:Requirement Review 需求审核流程
# ============================================================
def _load_requirement_by_bid(bid_document_id, current_user, bid_only=False) \
        -> tuple:
    """
    内部工具:按 bid_id 加载 BidDocument + BidRequirement,校验权限

    :return: (bid_document, bid_requirement)
    """
    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')
    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')
    _check_bid_permission(bid_document, current_user)
    requirement = bid_document.requirement
    if bid_only:
        return bid_document, requirement
    if not requirement:
        raise NotFoundError('招标需求未生成(请先解析招标文件)')
    return bid_document, requirement


def submit_requirement_for_review(bid_document_id, current_user):
    """
    提交审核: draft → reviewing

    权限:
    - admin / contract_manager:任意提交
    - employee:仅可提交自己上传的,且必须是 draft 状态
    """
    bid_doc, req = _load_requirement_by_bid(bid_document_id, current_user)

    if req.status not in BidRequirement.REVIEW_TRANSITIONS \
            or 'reviewing' not in BidRequirement.REVIEW_TRANSITIONS.get(req.status, ()):
        raise BusinessError(
            f'当前需求状态为 {req.status},不允许提交审核(仅 draft 可提交)'
        )

    req.status = 'reviewing'
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Bid:review] 提交审核失败: req_no=%s', req.requirement_no)
        raise BusinessError('提交审核失败,请重试')

    logger.info('[Bid:review] 提交审核: req_no=%s operator=%s',
                req.requirement_no, current_user.get('username'))
    return req.to_dict(include_data=True)


def review_requirement(bid_document_id, current_user, approved: bool,
                       comment: str = None):
    """
    审核: reviewing → approved(通过) / draft(驳回)

    权限:
    - admin / contract_manager:可审核(employee 无审核权限,API 层 role_required 拦截)
    """
    # 权限兜底:employee 无审核权限
    if current_user.get('role') not in ('admin', 'contract_manager'):
        raise BusinessError('当前用户无审核权限')

    bid_doc, req = _load_requirement_by_bid(bid_document_id, current_user)

    if req.status != 'reviewing':
        raise BusinessError(
            f'当前需求状态为 {req.status},不允许审核(仅 reviewing 可审核)'
        )

    target = 'approved' if approved else 'draft'
    if target not in BidRequirement.REVIEW_TRANSITIONS.get('reviewing', ()):
        raise BusinessError(f'非法状态跳转: reviewing → {target}')

    req.status = target
    # 驳回时:把 comment 附加到 error_message 供前端展示(不覆盖原错误)
    if not approved and comment:
        req.error_message = f'[审核驳回] {comment[:500]}'
    elif approved:
        req.error_message = None

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Bid:review] 审核失败: req_no=%s', req.requirement_no)
        raise BusinessError('审核失败,请重试')

    logger.info('[Bid:review] 审核完成: req_no=%s result=%s operator=%s',
                req.requirement_no, target, current_user.get('username'))
    return req.to_dict(include_data=True)


def update_requirement_status(bid_document_id, current_user, new_status: str):
    """
    通用状态更新接口(提供给前端直接调,内部严格走 REVIEW_TRANSITIONS)

    等价于:
    - draft→reviewing = submit_requirement_for_review
    - reviewing→approved / reviewing→draft = review_requirement
    """
    if not new_status:
        raise ValidationError('目标状态为空')
    if new_status not in BidRequirement.VALID_STATUSES:
        raise ValidationError(
            f'非法状态,允许: {", ".join(BidRequirement.VALID_STATUSES)}'
        )

    if new_status == 'reviewing':
        return submit_requirement_for_review(bid_document_id, current_user)
    if new_status in ('approved', 'draft'):
        bid_doc, req = _load_requirement_by_bid(bid_document_id, current_user)
        if req.status == 'reviewing':
            return review_requirement(bid_document_id, current_user,
                                      approved=(new_status == 'approved'))
        # 其他情况下从 status 到 draft 的切换(如 approved→draft 不允许,由 REVIEW_TRANSITIONS 限制)
        raise BusinessError(
            f'当前状态 {req.status} 不能直接切换到 {new_status},请通过审核流程操作'
        )

    raise BusinessError(f'不允许切换到 {new_status}')


# ============================================================
# 查询接口
# ============================================================
def get_bid_requirement(bid_document_id, current_user):
    """
    查询招标需求(15 字段 Requirement)

    权限:
    - admin / contract_manager:可见任意
    - employee:仅可见自己上传的(他人返回 404 防枚举)

    :param bid_document_id: 招标文件 ID
    :param current_user: {'id','role'}
    :return: dict 招标需求信息(含 requirement_data 15 字段 + 质量指标)
    """
    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')

    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')
    _check_bid_permission(bid_document, current_user)

    requirement = bid_document.requirement
    if not requirement:
        raise NotFoundError('招标需求未生成(请先解析招标文件)')

    return requirement.to_dict(include_data=True)


def list_bid_documents(current_user, page=1, size=20, parse_status=None,
                       keyword=None):
    """
    招标文件分页列表

    支持:分页 / parse_status 过滤 / 关键字搜索(title + bid_no)/
         按 created_time DESC 排序

    权限:
    - admin / contract_manager:可见全部
    - employee:仅可见 uploader_id == 自己 的招标文件

    :param current_user: {'id','role'}
    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param parse_status: 解析状态过滤(pending / processing / success / failed,可选)
    :param keyword: 关键字(title / bid_no 模糊)
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

    if parse_status and parse_status not in BidDocument.VALID_PARSE_STATUSES:
        raise ValidationError(
            f'解析状态非法,允许: {", ".join(BidDocument.VALID_PARSE_STATUSES)}'
        )

    # ---------- 查询构建 ----------
    query = BidDocument.query.options(joinedload(BidDocument.uploader))

    # 权限过滤:employee 仅可见自己上传的
    if current_user and current_user.get('role') == 'employee':
        query = query.filter_by(uploader_id=current_user['id'])

    if parse_status:
        query = query.filter_by(parse_status=parse_status)

    if keyword:
        kw = f'%{keyword}%'
        query = query.filter(
            db.or_(BidDocument.title.like(kw), BidDocument.bid_no.like(kw))
        )

    query = query.order_by(BidDocument.created_time.desc())

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    # 列表场景:不含全文,含 requirement 概要
    items = [
        b.to_dict(include_text=False, include_requirement=True)
        for b in pagination.items
    ]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def get_bid_document_detail(bid_document_id, current_user, include_text=False):
    """
    招标文件详情

    权限:
    - admin / contract_manager:可见任意
    - employee:仅可见自己上传的(他人返回 404)

    :param bid_document_id: 招标文件 ID
    :param current_user: {'id','role'}
    :param include_text: 是否返回 text_content 全文(详情页可传 True)
    :return: dict 招标文件信息(含 requirement 概要,可选全文)
    """
    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')

    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')
    _check_bid_permission(bid_document, current_user)

    return bid_document.to_dict(include_text=include_text, include_requirement=True)


# ============================================================
# 删除招标文件(admin / contract_manager)
# ============================================================
def delete_bid_document(bid_document_id, current_user):
    """
    删除招标文件

    流程:
    1. 校验存在 + 权限(admin / contract_manager;employee 404 防枚举)
    2. 校验无关联的 GeneratedProposal(若有,提示先删除生成记录,避免孤儿)
    3. 物理删除文件
    4. 软删/硬删 BidDocument + cascade delete BidRequirement
       (cascade='all, delete-orphan' 自动级联删除 Requirement)

    权限:
    - admin / contract_manager:可删除任意招标文件
    - employee:不可删除(API 层 @role_required 拦截;此处兜底 404)

    :param bid_document_id: 招标文件 ID
    :param current_user: {'id','role','username'}
    :return: dict {id, bid_no, status}
    """
    # 权限兜底(API 层已拦截,此处防御)
    if current_user.get('role') not in ('admin', 'contract_manager'):
        raise NotFoundError('招标文件不存在')

    try:
        bid_id = int(bid_document_id)
    except (TypeError, ValueError):
        raise ValidationError('招标文件 ID 非法')

    bid_document = db.session.get(BidDocument, bid_id)
    if not bid_document:
        raise NotFoundError('招标文件不存在')

    # ---------- 校验关联的生成记录 ----------
    proposals_count = bid_document.proposals.count()
    if proposals_count > 0:
        raise BusinessError(
            f'该招标文件存在 {proposals_count} 条投标生成记录,请先删除生成记录后再删除招标文件'
        )

    file_path = bid_document.file_path
    bid_no = bid_document.bid_no

    # ---------- 删除 DB 记录(cascade 删除 Requirement) ----------
    try:
        db.session.delete(bid_document)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Bid:delete] 删除失败: bid_no=%s', bid_no)
        raise BusinessError('删除招标文件失败,请重试')

    # ---------- 物理删除文件(DB 已提交,文件删除失败仅告警) ----------
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            logger.warning('[Bid:delete] 招标文件物理删除失败(记录已删): %s', file_path)

    logger.info('[Bid:delete] 招标文件已删除: bid_no=%s operator=%s',
                bid_no, current_user.get('username'))

    return {
        'id': bid_id,
        'bid_no': bid_no,
        'status': 'deleted',
    }
