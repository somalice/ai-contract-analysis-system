"""
分析任务业务服务(Sprint 3 - v0.5.0)

职责:
- trigger_analysis:触发合同分析(创建 Task + Document + 同步执行 Pipeline)
- get_task:查询任务状态(含 stages_log 进度)
- get_contract_fields:获取合同字段(优先 contract_fields,降级 analysis_result)

权限设计(与 contract_service 一致):
- admin / contract_manager:可分析 / 查询任意合同
- employee:仅可分析 / 查询 creator_id == 自己 的合同

调用链:
api/contract/routes.py(analysis endpoints)
  → analysis_service
    → models/{document,analysis_task,contract_field}.py
    → ai/pipeline/run_pipeline
    → ai/pipeline/stages/*

约束:
- 本层不直接渲染模板、不访问 request 对象
- Pipeline 同步执行(Sprint 3 不引入 Celery)
- AI 失败 → Task=failed,但 Task 记录 + Document 文本仍落库(可重跑)
- 禁止 print() / return str(e)
"""
import os
import uuid
from datetime import datetime
from flask import current_app

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.contract import Contract
from app.models.document import Document
from app.models.analysis_task import AnalysisTask
from app.models.contract_field import ContractField
from app.utils.file_utils import get_file_type
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.ai.pipeline import PipelineContext, run_pipeline


# ---------- 配置常量 ----------
# Task 状态 → Contract.analysis_status 映射(保持前端兼容)
_TASK_STATUS_TO_ANALYSIS = {
    'pending': 'processing',
    'running': 'processing',
    'success': 'completed',
    'failed': 'failed',
}


def _generate_task_no():
    """
    生成任务编号:AT-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'AT-{timestamp}-{suffix}'


def _get_or_create_document(contract):
    """
    获取或创建合同关联的 Document 记录

    Sprint 3 策略:合同上传时不再自动创建 Document(避免修改 contract_service 太多);
    首次触发分析时按需创建,从 Contract.file_path/file_name/file_size 复制元信息。

    :param contract: Contract 模型实例
    :return: Document 模型实例
    """
    # 查关联 Document(取第一个;本阶段 1:1)
    document = contract.documents.first() if hasattr(contract, 'documents') else None
    if document:
        return document

    # 从 Contract 创建 Document
    file_type = get_file_type(contract.file_name)
    document = Document(
        contract_id=contract.id,
        file_name=contract.file_name,
        file_path=contract.file_path,
        file_size=contract.file_size,
        file_type=file_type,
        page_count=0,
        text_content=None,
        text_length=0,
        extract_method='none',
    )
    db.session.add(document)
    db.session.flush()  # 拿到 id
    logger.info('Document 创建: id=%s contract_id=%s', document.id, contract.id)
    return document


def _check_contract_permission(contract, current_user):
    """
    权限校验:employee 仅可操作自己的合同
    (admin / contract_manager 无限制)
    """
    if current_user and current_user.get('role') == 'employee' \
            and contract.creator_id != current_user['id']:
        raise NotFoundError('合同不存在')  # 404 防枚举,不泄露存在性


def trigger_analysis(contract_id, current_user):
    """
    触发合同分析

    流程:
    1. 校验合同存在 + 权限
    2. 获取/创建 Document
    3. 创建 AnalysisTask(pending)
    4. 创建 PipelineContext
    5. 同步执行 run_pipeline
    6. 提交事务(Task + Document + ContractField)
    7. 回写 Contract.analysis_status

    :param contract_id: 合同 ID
    :param current_user: {'id','role','username'}
    :return: dict 任务信息(含 stages_log)
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

    # ---------- 2. 获取/创建 Document ----------
    document = _get_or_create_document(contract)

    # ---------- 3. 创建 AnalysisTask ----------
    task = AnalysisTask(
        task_no=_generate_task_no(),
        contract_id=contract.id,
        document_id=document.id,
        status='pending',
        current_stage=None,
        stages_log=[],
        error_message=None,
        triggered_by=current_user['id'],
        started_time=None,
        finished_time=None,
    )
    db.session.add(task)
    db.session.flush()  # 拿到 task.id

    logger.info('分析任务创建: task_no=%s contract_id=%s triggered_by=%s',
                task.task_no, contract.id, current_user.get('username'))

    # ---------- 4. 创建 PipelineContext ----------
    ctx = PipelineContext(
        file_path=document.file_path,
        file_type=document.file_type,
        document=document,
        task=task,
    )

    # ---------- 5. 同步执行 Pipeline ----------
    try:
        result = run_pipeline(ctx)
    except Exception as e:
        # Pipeline 内部异常兜底(正常情况下 runner 不会抛出)
        logger.exception('Pipeline 执行异常: task_no=%s', task.task_no)
        task.status = 'failed'
        task.error_message = f'Pipeline 执行异常: {e}'
        task.finished_time = datetime.utcnow()
        result = {
            'status': 'failed',
            'current_stage': task.current_stage,
            'error': task.error_message,
            'stages_log': ctx.stages_log,
        }

    # ---------- 6. 回写 Contract.analysis_status ----------
    contract.analysis_status = _TASK_STATUS_TO_ANALYSIS.get(
        task.status, 'processing')

    # ---------- 7. 提交事务 ----------
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('分析任务提交失败: task_no=%s', task.task_no)
        raise BusinessError('分析任务提交失败,请重试')

    logger.info('分析任务完成: task_no=%s status=%s duration=%ss',
                task.task_no, task.status,
                (task.finished_time - task.started_time).total_seconds()
                if task.started_time and task.finished_time else 0)

    return task.to_dict(include_log=True)


def get_task(task_id, current_user):
    """
    查询任务状态

    权限:通过 contract_id 关联校验(employee 仅可查自己合同的任务)

    :param task_id: 任务 ID
    :param current_user: {'id','role'}
    :return: dict 任务信息(含 stages_log)
    """
    try:
        tid = int(task_id)
    except (TypeError, ValueError):
        raise ValidationError('任务 ID 非法')

    task = db.session.get(AnalysisTask, tid)
    if not task:
        raise NotFoundError('任务不存在')

    # 通过 contract 校验权限
    contract = db.session.get(Contract, task.contract_id)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    return task.to_dict(include_log=True)


def get_contract_fields(contract_id, current_user):
    """
    获取合同字段

    读取顺序:
    1. 优先读最新成功任务(success)的 contract_fields
    2. 若无成功任务,读最新任意任务的 contract_fields(可能字段全 null)
    3. 若无任何 contract_fields,降级读 Contract.analysis_result(Sprint 2 旧合同)
    4. 都没有则返回空

    :param contract_id: 合同 ID
    :param current_user: {'id','role'}
    :return: dict
        - fields: 字段列表
        - task: 最近任务信息 {id, task_no, status}(可能为 null)
        - source: 'contract_fields' / 'legacy_json' / 'empty'
    """
    # ---------- 校验 ----------
    try:
        cid = int(contract_id)
    except (TypeError, ValueError):
        raise ValidationError('合同 ID 非法')

    contract = db.session.get(Contract, cid)
    if not contract:
        raise NotFoundError('合同不存在')
    _check_contract_permission(contract, current_user)

    # ---------- 1. 查最新任务(优先 success) ----------
    latest_task = (
        AnalysisTask.query
        .filter_by(contract_id=cid)
        .order_by(AnalysisTask.created_time.desc())
        .first()
    )

    fields = []
    source = 'empty'

    if latest_task:
        # 优先读 success 任务的字段;若最新不是 success,也读最新的(可能 failed 但有部分字段)
        task_to_read = latest_task
        if latest_task.status != 'success':
            success_task = (
                AnalysisTask.query
                .filter_by(contract_id=cid, status='success')
                .order_by(AnalysisTask.created_time.desc())
                .first()
            )
            if success_task:
                task_to_read = success_task

        field_records = (
            ContractField.query
            .filter_by(contract_id=cid, task_id=task_to_read.id)
            .order_by(ContractField.id)
            .all()
        )
        if field_records:
            fields = [f.to_dict() for f in field_records]
            source = 'contract_fields'

    # ---------- 2. 降级:读 Sprint 2 analysis_result JSON ----------
    if not fields and contract.analysis_result:
        legacy = contract.analysis_result
        # Sprint 2 字段:contract_name / party_a / party_b / amount / signing_date
        # 映射到 Sprint 3 字段名(signing_date → sign_date)
        legacy_map = {
            'contract_no': None,  # Sprint 2 未提取
            'contract_name': legacy.get('contract_name'),
            'party_a': legacy.get('party_a'),
            'party_b': legacy.get('party_b'),
            'amount': legacy.get('amount'),
            'sign_date': legacy.get('signing_date'),  # 旧字段名 signing_date
            'payment_method': None,  # Sprint 2 未提取
            'valid_period': None,    # Sprint 2 未提取
        }
        # 仅当 legacy 有 error 字段或全部为空时,不降级
        if legacy.get('error'):
            # 旧分析失败,不降级
            pass
        else:
            fields = [
                {
                    'field_name': name,
                    'field_label': ContractField.FIELD_LABELS.get(name, name),
                    'field_value': val if val else None,  # 空字符串转 null
                    'confidence': 0.0,  # 旧数据无置信度
                    'source_text': None,
                }
                for name, val in legacy_map.items()
            ]
            source = 'legacy_json'

    return {
        'fields': fields,
        'task': {
            'id': latest_task.id,
            'task_no': latest_task.task_no,
            'status': latest_task.status,
        } if latest_task else None,
        'source': source,
        'contract_id': cid,
    }
