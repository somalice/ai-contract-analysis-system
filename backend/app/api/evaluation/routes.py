"""
AI 评估报告 API(Sprint 8 - v1.0.0 企业级 AI 增强)

- GET  /api/v1/evaluation/report        即时生成评估报告(可选持久化? 默认否;query param persist=true 可保存)
- POST /api/v1/evaluation/report        生成 + 持久化快照(admin)
- GET  /api/v1/evaluation/reports       快照列表(admin)
- GET  /api/v1/evaluation/reports/{id}  快照详情(admin)

Sprint 8.5 新增(RAG 三态评估 + 前端评估中心对接):
- GET  /api/v1/evaluation/summary       返回最新评估 summary(PASS/PENDING/FAIL 三态 + RAG 4 指标 + AI 稳定性)
- GET  /api/v1/evaluation/history       历史评估快照列表(精简字段,供前端历史表格)
- GET  /api/v1/evaluation/history/{id}  历史快照详情(完整 metrics)
- POST /api/v1/evaluation/run           执行一次完整评估(admin, RAG + AI + Summary)

权限:所有接口仅 admin。
"""
from datetime import datetime
from flask import request, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.api.evaluation import evaluation_bp
from app.decorators.role_required import role_required
from app.services import evaluation_service, evaluation_run_service
from app.utils import response
from app.utils.exceptions import ValidationError


def _parse_period():
    """从 query 解析 start_time/end_time (YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD)"""
    s = (request.args.get('start_time')
         or (request.get_json(silent=True) or {}).get('start_time'))
    e = (request.args.get('end_time')
         or (request.get_json(silent=True) or {}).get('end_time'))
    start = end = None
    if s:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                start = datetime.strptime(str(s).strip(), fmt)
                break
            except ValueError:
                continue
        if start is None:
            raise ValidationError('start_time 格式非法,示例:YYYY-MM-DD HH:MM:SS')
    if e:
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                end = datetime.strptime(str(e).strip(), fmt)
                break
            except ValueError:
                continue
        if end is None:
            raise ValidationError('end_time 格式非法,示例:YYYY-MM-DD HH:MM:SS')
    return start, end


@evaluation_bp.route('/report', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_report_online():
    try:
        start, end = _parse_period()
    except ValidationError as e:
        return response.error(str(e), 400)
    persist = request.args.get('persist', '').lower() in ('1', 'true', 'yes')
    current_user = get_jwt_identity() or {}
    uid = current_user.get('id') if isinstance(current_user, dict) else None
    try:
        data = evaluation_service.generate_report(start, end, uid, persist=persist)
    except Exception as e:
        return response.error(f'生成报告失败: {e}', 500)
    return response.success(data)


@evaluation_bp.route('/report', methods=['POST'])
@jwt_required()
@role_required('admin')
def post_report_and_save():
    try:
        start, end = _parse_period()
    except ValidationError as e:
        return response.error(str(e), 400)
    current_user = get_jwt_identity() or {}
    uid = current_user.get('id') if isinstance(current_user, dict) else None
    try:
        data = evaluation_service.generate_report(start, end, uid, persist=True)
    except Exception as e:
        return response.error(f'保存报告失败: {e}', 500)
    return response.success(data, '已生成并保存快照', 201)


@evaluation_bp.route('/reports', methods=['GET'])
@jwt_required()
@role_required('admin')
def list_reports():
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    data = evaluation_service.list_reports(page=page, size=size)
    return response.success(data)


@evaluation_bp.route('/reports/<int:report_id>', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_report(report_id):
    data = evaluation_service.get_report(report_id)
    if data is None:
        return response.error('报告不存在', 404)
    return response.success(data)


# ============================================================
# Sprint 8.5 新增:RAG 三态评估 + 前端评估中心对接
# ============================================================
@evaluation_bp.route('/summary', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_evaluation_summary():
    """返回最新评估 summary(PASS/PENDING/FAIL 三态 + RAG 4 指标 + AI 稳定性 + 测试环境说明)。"""
    try:
        data = evaluation_run_service.get_latest_summary()
    except Exception as e:
        return response.error(f'读取评估 summary 失败: {e}', 500)
    if data is None:
        return response.success(
            {'status': 'PENDING', 'reason': '尚未执行过评估,请点击"执行评估"按钮生成首份报告。'},
            '暂无评估数据',
        )
    return response.success(data)


@evaluation_bp.route('/history', methods=['GET'])
@jwt_required()
@role_required('admin')
def list_evaluation_history():
    """历史评估快照列表(精简字段,供前端历史表格展示)。"""
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    try:
        data = evaluation_run_service.list_history(page=page, size=size)
    except Exception as e:
        return response.error(f'查询历史评估失败: {e}', 500)
    return response.success(data)


@evaluation_bp.route('/history/<int:report_id>', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_evaluation_history_detail(report_id):
    """历史快照详情(完整 metrics)。"""
    try:
        data = evaluation_run_service.get_history_detail(report_id)
    except Exception as e:
        return response.error(f'查询评估详情失败: {e}', 500)
    if data is None:
        return response.error('评估快照不存在', 404)
    return response.success(data)


@evaluation_bp.route('/run', methods=['POST'])
@jwt_required()
@role_required('admin')
def run_evaluation():
    """
    执行一次完整 AI 评估(admin) - Sprint 8.6.1 异步化。

    请求体(均可选):
    {
      "mode": "quick",            // quick(10题快速验证) | standard(51题完整评估) | full(51题+LLM Judge)
      "sample_size": null,        // 显式覆盖题数(可选)
      "use_llm_answer": false,    // 显式覆盖是否 LLM 生成(可选;full 模式默认 true)
      "period_days": 60,          // AI 调用日志统计天数
      "evaluation_mode": null     // 兼容旧参数 quick|production(可选,优先级低于 mode)
    }

    立即返回(不阻塞,HTTP 202):
    {
      "task_id": "EVALTASK-...",
      "status": "pending",        // 随后后台置 running
      "progress": 0,
      "stage": "creating",
      "evaluation_mode": "quick",
      "sample_size": 10,
      "use_llm_answer": false
    }
    前端轮询 GET /evaluation/task/{task_id} 获取实时进度,任务 success 后刷新 GET /evaluation/summary。
    """
    payload = request.get_json(silent=True) or {}
    current_user = get_jwt_identity() or {}
    uid = current_user.get('id') if isinstance(current_user, dict) else None

    # 显式覆盖参数(宽松校验,非法值回退默认)
    sample_size = payload.get('sample_size')
    if sample_size is not None:
        try:
            sample_size = int(sample_size)
            if sample_size <= 0:
                sample_size = None
        except (TypeError, ValueError):
            sample_size = None
    use_llm = payload.get('use_llm_answer')
    if use_llm is not None:
        use_llm = bool(use_llm)

    # 评估模式:优先 mode(quick/standard/full);兼容旧 evaluation_mode(quick/production)
    mode = payload.get('mode')
    if mode not in evaluation_run_service.EVALUATION_MODES:
        legacy_em = payload.get('evaluation_mode', 'quick')
        mode = 'full' if legacy_em == 'production' else 'quick'

    try:
        task = evaluation_run_service.create_evaluation_task(
            user_id=uid,
            evaluation_mode=mode,
            sample_size=sample_size,
            use_llm_answer=use_llm,
        )
    except Exception as e:
        return response.error(f'创建评估任务失败: {e}', 500)
    # HTTP 202(已接受) + body code=200,兼容前端拦截器(仅认 code===200)
    resp = make_response(response.success(task, '评估任务已提交,后台执行中', 200))
    resp.status_code = 202
    return resp


@evaluation_bp.route('/task/<string:task_id>', methods=['GET'])
@jwt_required()
@role_required('admin')
def get_evaluation_task(task_id):
    """
    查询评估异步任务状态(Sprint 8.6.1,供前端轮询进度)。

    返回:
    {
      "task_id": "...",
      "status": "pending|running|success|failed",
      "progress": 0-100,
      "stage": "creating|rag_evaluation|ai_metrics|agent_metrics|report_generation|completed|failed",
      "report_id": "EVAL-..." | null,
      "start_time": ..., "end_time": ..., "error": null,
      "evaluation_mode": "quick|standard|full",
      "sample_size": 10, "use_llm_answer": false
    }
    """
    try:
        data = evaluation_run_service.get_evaluation_task(task_id)
    except Exception as e:
        return response.error(f'查询评估任务失败: {e}', 500)
    if data is None:
        return response.error('评估任务不存在', 404)
    return response.success(data)

