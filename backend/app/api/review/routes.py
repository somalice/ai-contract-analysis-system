"""
合同审核报告 API(Blueprint)- Sprint 5 v0.7.0 / v0.7.1 增强

接口:
- GET  /api/v1/reviews              全局审核报告列表(分页,供"合同审核"菜单页)
- GET  /api/v1/reviews/{id}         查询审核报告详情(含 risks / tool_calls_log / agent_trace)
- GET  /api/v1/reviews/{id}/trace   查询 Agent 执行 Trace(v0.7.1 新增,供前端 Timeline)

另:POST /api/v1/contracts/{id}/review 与 GET /api/v1/contracts/{id}/reviews
   在 api/contract/routes.py 的 contract_api_bp 中注册(资源嵌套于合同)。

职责:
- 参数接收与校验
- 调用 review_service
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接调用 Agent / LLM / Retriever
- API 层写业务逻辑(均下沉至 review_service)

权限:
- JWT 认证
- employee 仅可查自己合同的审核(他人返回 404 防枚举)
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import review_service
from app.utils.response import success

review_bp = Blueprint('review', __name__)


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


@review_bp.route('', methods=['GET'])
@jwt_required()
def list_reviews():
    """
    全局审核报告列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - risk_level: 风险等级过滤(high/medium/low/none,可选)
      - status: 状态过滤(pending/running/success/failed,可选)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见全部审核
    - employee:仅可见自己合同的审核(后端过滤)

    响应:
    - data.items:审核列表(含关联合同摘要,不含 risks 详情)
      [{id, review_no, contract_id, status, risk_level, iterations,
        contract:{id,title,contract_no}, created_time, ...}]
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    risk_level = request.args.get('risk_level') or None
    status = request.args.get('status') or None

    current_user = _get_current_user()
    result = review_service.list_reviews(
        current_user, page=page, size=size,
        risk_level=risk_level, status=status,
    )
    return success(data=result)


@review_bp.route('/<int:review_id>', methods=['GET'])
@jwt_required()
def get_review(review_id):
    """
    查询审核报告详情(需 JWT)

    返回:
    - data.review:审核报告信息
      - id / review_no / contract_id / task_id
      - status:pending / running / success / failed
      - risk_level:high / medium / low / none(成功时填)
      - summary:审核总结
      - risks:风险详情数组 [{type, severity, description, suggestion, evidence, references}]
      - tool_calls_log:Agent 工具调用轨迹(审计用)
      - iterations / llm_error / error_message
      - started_time / finished_time / created_time / updated_time

    权限:
    - admin / contract_manager:可查任意审核
    - employee:仅可查自己合同的审核(他人返回 404)
    """
    current_user = _get_current_user()
    review = review_service.get_review(review_id, current_user)
    return success(data={'review': review})


@review_bp.route('/<int:review_id>/trace', methods=['GET'])
@jwt_required()
def get_review_trace(review_id):
    """
    查询审核报告 Agent Trace(v0.7.1 新增,需 JWT)

    供前端 ReviewDetail 页 Agent 执行过程 Timeline 展示:
      - Thought → Decision → Action → Observation → Duration → Status

    返回:
    - data.trace:Agent 执行 Trace 摘要
      - id / review_no / contract_id / status / risk_level / iterations
      - agent_trace:每步 {step, thought, decision, action, tool_name,
                          tool_input, observation, start_time, end_time,
                          duration_ms, status, error_message}
      - trace_summary:{steps, total_ms, llm_ms, tool_ms,
                       tool_stats:{...}, llm_stats:{...}}
      - llm_error / llm_error_type
      - started_time / finished_time

    权限:
    - admin / contract_manager:可查任意审核
    - employee:仅可查自己合同的审核(他人返回 404)
    """
    current_user = _get_current_user()
    trace = review_service.get_trace(review_id, current_user)
    return success(data={'trace': trace})
