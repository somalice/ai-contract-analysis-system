"""
系统日志 API(Sprint 8 - v1.0.0 企业级 AI 增强)

对应 API_DESIGN §10 系统日志 API:GET /api/v1/logs。
细分:
- GET /api/v1/logs/operations    操作审计日志
- GET /api/v1/logs/operations/{id}
- GET /api/v1/logs/ai            AI 调用日志
- GET /api/v1/logs/ai/{id}

权限:所有日志接口仅 admin 可访问。
"""
from datetime import datetime
from flask import request
from flask_jwt_extended import jwt_required

from app.api.log import log_bp
from app.decorators.role_required import role_required
from app.services import ai_log_service
from app.services.operation_log_service import (
    list_operation_logs,
    get_operation_log,
)
from app.utils import response
from app.utils.exceptions import ValidationError


def _parse_datetime(val):
    if not val:
        return None
    val = str(val).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise ValidationError(f'时间格式非法: {val}, 示例: YYYY-MM-DD HH:MM:SS')


@log_bp.route('/operations', methods=['GET'])
@jwt_required()
@role_required('admin')
def list_operations():
    try:
        user_id = request.args.get('user_id')
        operation_type = request.args.get('operation_type')
        status = request.args.get('status')
        target_type = request.args.get('target_type')
        start_time = _parse_datetime(request.args.get('start_time'))
        end_time = _parse_datetime(request.args.get('end_time'))
        page = request.args.get('page', 1)
        size = request.args.get('size', 20)
        data = list_operation_logs(
            user_id=user_id, operation_type=operation_type, status=status,
            target_type=target_type, start_time=start_time, end_time=end_time,
            page=page, size=size,
        )
    except ValidationError as e:
        return response.error(str(e), 400)
    return response.success(data)


@log_bp.route('/operations/<int:log_id>', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_operation(log_id):
    data = get_operation_log(log_id)
    if data is None:
        return response.error('日志不存在', 404)
    return response.success(data)


@log_bp.route('/ai', methods=['GET'])
@jwt_required()
@role_required('admin')
def list_ai_logs():
    try:
        agent_type = request.args.get('agent_type')
        status = request.args.get('status')
        user_id = request.args.get('user_id')
        start_time = _parse_datetime(request.args.get('start_time'))
        end_time = _parse_datetime(request.args.get('end_time'))
        page = request.args.get('page', 1)
        size = request.args.get('size', 20)
    except ValidationError as e:
        return response.error(str(e), 400)
    data = ai_log_service.list_ai_logs(
        agent_type=agent_type, status=status, user_id=user_id,
        start_time=start_time, end_time=end_time, page=page, size=size,
    )
    return response.success(data)


@log_bp.route('/ai/<int:log_id>', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_ai_log(log_id):
    data = ai_log_service.get_ai_log(log_id)
    if data is None:
        return response.error('日志不存在', 404)
    return response.success(data)
