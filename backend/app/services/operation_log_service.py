"""
操作审计日志查询服务(Sprint 8 - v1.0.0 企业级 AI 增强)

职责:仅提供 Logs API 查询 OperationLog。写入由 middleware/audit_middleware.py 负责。

所有方法不抛出业务异常。
"""
from app.extensions.db import db
from app.extensions.logger import logger
from app.models.operation_log import OperationLog


def list_operation_logs(user_id=None, operation_type=None, status=None, target_type=None,
                         start_time=None, end_time=None, page=1, size=20):
    page, size = _normalize_paging(page, size)
    q = OperationLog.query
    if user_id:
        try:
            q = q.filter(OperationLog.user_id == int(user_id))
        except (TypeError, ValueError):
            pass
    if operation_type:
        q = q.filter_by(operation_type=operation_type)
    if status:
        q = q.filter_by(status=status)
    if target_type:
        q = q.filter_by(target_type=target_type)
    if start_time:
        q = q.filter(OperationLog.created_time >= start_time)
    if end_time:
        q = q.filter(OperationLog.created_time <= end_time)
    total = q.count()
    items = (
        q.order_by(OperationLog.created_time.desc())
        .offset((page - 1) * size).limit(size)
        .all()
    )
    return {
        'total': total,
        'page': page,
        'size': size,
        'items': [l.to_dict() for l in items],
    }


def get_operation_log(log_id):
    try:
        lid = int(log_id)
    except (TypeError, ValueError):
        return None
    log = db.session.get(OperationLog, lid)
    return log.to_dict() if log else None


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
