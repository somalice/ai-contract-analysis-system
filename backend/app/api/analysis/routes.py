"""
分析任务 API(Blueprint)- Sprint 3 v0.5.0

接口:
- GET /api/v1/analysis/{task_id}  查询分析任务状态(含 stages_log 进度)

职责:
- 参数接收与校验
- 调用 analysis_service.get_task
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接调用 Pipeline / LLM
- API 层写业务逻辑

权限:
- 通过 contract_id 关联校验(employee 仅可查自己合同的任务)
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import analysis_service
from app.utils.response import success

analysis_bp = Blueprint('analysis', __name__)


def _get_current_user():
    """
    从 JWT 提取当前用户信息
    :return: dict {'id': int, 'role': str, 'username': str}
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return {
        'id': user_id,
        'role': claims.get('role'),
        'username': claims.get('username'),
    }


@analysis_bp.route('/<int:task_id>', methods=['GET'])
@jwt_required()
def get_analysis_task(task_id):
    """
    查询分析任务状态(需 JWT)

    返回:
    - data.task:任务信息
      - id / task_no / contract_id / document_id
      - status:pending / running / success / failed
      - current_stage:extract / ocr / clean / chunk / llm / save
      - stages_log:各 Stage 执行日志
      - error_message:失败原因
      - started_time / finished_time

    权限:
    - admin / contract_manager:可查任意任务
    - employee:仅可查自己合同的任务(他人任务返回 404)
    """
    current_user = _get_current_user()
    task = analysis_service.get_task(task_id, current_user)
    return success(data={'task': task})
