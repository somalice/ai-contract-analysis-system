"""
合同模块 API(Blueprint)
对应 legacy index() 路由(行 526-666)。

职责:
- 请求方法分发(GET/POST)
- 参数校验(file 存在性、文件名非空)
- 调用 Service(document_service.process_upload)
- 回放 flash 消息
- 渲染模板

禁止:在本层直接调用 OCR / LLM / pdfplumber(必须经 Service 编排)。
"""
from flask import Blueprint, render_template, request, flash
from app.services.document_service import process_upload
from app.utils.file_utils import allowed_file

contract_bp = Blueprint('contract', __name__)


@contract_bp.route('/', methods=['GET', 'POST'])
def index():
    """
    首页:合同上传与 AI 分析结果展示
    - GET: 显示上传表单(空)
    - POST: 校验 → 调用 Service 处理 → 回放 flash → 渲染结果
    """
    # 初始化提取的文本、文件名和提取的字段(与 legacy 一致)
    extracted_text = ""
    filename = ""
    contract_fields = None
    ocr_method = ""

    if request.method == 'POST':
        # 检查请求中是否包含文件部分
        if 'file' not in request.files:
            flash('未选择文件！', 'danger')
            return render_template('index.html', text="", filename="", fields=None, ocr_method="")

        # 获取上传的文件对象
        file = request.files['file']

        # 检查文件名是否为空
        if file.filename == '':
            flash('请选择一个文件！', 'danger')
            return render_template('index.html', text="", filename="", fields=None, ocr_method="")

        # 检查文件类型是否允许
        if file and allowed_file(file.filename):
            # 调用 Service 处理上传(业务下沉,API 层不直接调用 OCR/LLM)
            result = process_upload(file)

            # 回放 Service 返回的 flash 消息(保持顺序与 legacy 一致)
            for category, message in result['flashes']:
                flash(message, category)

            extracted_text = result['text']
            filename = result['filename']
            contract_fields = result['fields']
            ocr_method = result['ocr_method']

    # GET 请求或处理完成后,渲染首页并传递提取的文本和字段
    return render_template('index.html',
                           text=extracted_text,
                           filename=filename,
                           fields=contract_fields,
                           ocr_method=ocr_method)


# ============================================================
# Sprint 2 - v0.4.0:合同生命周期管理 RESTful API
# ============================================================
# 独立 Blueprint(命名 'contract_api',区别于上方 'contract' HTML 路由)
# 注册前缀:/api/v1/contracts(在 create_app 中通过 url_prefix 注册)
#
# 接口:
# - POST   /upload               上传合同(需 JWT)
# - GET    ""                    合同分页列表(需 JWT)
# - GET    /<int:contract_id>    合同详情(需 JWT)
# - PATCH  /<int:contract_id>/status  更新合同状态(需 admin/contract_manager)
#
# 职责:
# - 参数接收与校验(file 存在性 / 文件名非空 / 类型允许 / 状态非空)
# - 调用 contract_service
# - 返回统一 Response
#
# 禁止:
# - API 层直接访问数据库
# - API 层直接调用 OCR / LLM
# - API 层写业务逻辑(均下沉至 contract_service)
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import contract_service
from app.utils.response import success
from app.utils.exceptions import ValidationError
from app.decorators.role_required import role_required

contract_api_bp = Blueprint('contract_api', __name__)


def _get_current_user():
    """
    从 JWT 提取当前用户信息(避免重复 DB 查询)

    JWT identity 为 str(user.id)(见 auth_service.login),需 int() 转换;
    role / username 通过 additional_claims 携带。

    :return: dict {'id': int, 'role': str, 'username': str}
    """
    user_id = int(get_jwt_identity())
    claims = get_jwt()
    return {
        'id': user_id,
        'role': claims.get('role'),
        'username': claims.get('username'),
    }


@contract_api_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_contract():
    """
    上传合同(需 JWT)

    请求:multipart/form-data
      - file: 合同文件(必填,pdf/png/jpg/jpeg)
      - contract_type: 合同类型(可选,默认"未分类")
      - title: 合同标题(可选,默认取文件名去扩展名)
      - description: 描述(可选)

    流程:上传 PDF → 保存文件 → 创建 Contract → 调用已有 AI 分析 → 返回合同信息
    """
    # 校验文件存在
    if 'file' not in request.files:
        raise ValidationError('未选择文件')
    file = request.files['file']
    # 校验文件名非空
    if not file.filename:
        raise ValidationError('文件名为空')
    # 校验文件类型允许
    if not allowed_file(file.filename):
        raise ValidationError('文件类型不允许')

    # 可选参数
    contract_type = request.form.get('contract_type') or '未分类'
    title = request.form.get('title') or None
    description = request.form.get('description') or None

    current_user = _get_current_user()
    contract = contract_service.create_contract(
        file, current_user,
        contract_type=contract_type, title=title, description=description
    )
    return success(data={'contract': contract}, message='上传成功')


@contract_api_bp.route('', methods=['GET'])
@jwt_required()
def list_contracts():
    """
    合同分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - keyword: 关键字(title / contract_no 模糊搜索)
      - status: 状态过滤(draft / reviewed / archived)
      - creator_id: 创建者过滤(仅 admin/contract_manager 生效,employee 强制只看自己)

    排序:created_time DESC
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    keyword = request.args.get('keyword') or None
    status = request.args.get('status') or None
    creator_id = request.args.get('creator_id') or None

    current_user = _get_current_user()
    result = contract_service.get_contract_list(
        page=page, size=size, keyword=keyword, status=status,
        creator_id=creator_id, current_user=current_user
    )
    return success(data=result)


@contract_api_bp.route('/<int:contract_id>', methods=['GET'])
@jwt_required()
def get_contract(contract_id):
    """
    合同详情(需 JWT)

    返回:合同信息 / 创建人 / 状态 / 文件信息 / AI 分析结果(读取已有结果)

    权限:
    - admin / contract_manager:可见任意合同
    - employee:仅可见自己的合同;他人合同返回 404(防 ID 枚举)
    """
    current_user = _get_current_user()
    contract = contract_service.get_contract_detail(contract_id, current_user)
    return success(data={'contract': contract})


@contract_api_bp.route('/<int:contract_id>/status', methods=['PATCH'])
@role_required('admin', 'contract_manager')
def update_contract_status(contract_id):
    """
    更新合同状态(需 admin / contract_manager 角色)

    请求体:application/json
      { "status": "reviewed" }

    状态机:仅允许 draft → reviewed → archived 单向流转
    - 非法跳转(如 draft → archived)返回 400
    - 同状态 / 回退 / 终态转出均禁止
    """
    data = request.get_json(silent=True) or {}
    target_status = data.get('status', '')
    if not target_status:
        raise ValidationError('状态不能为空')

    current_user = _get_current_user()
    contract = contract_service.update_contract_status(
        contract_id, target_status, current_user
    )
    return success(data={'contract': contract}, message='状态更新成功')


# ============================================================
# Sprint 3 - v0.5.0:Document Pipeline AI 解析接口
# ============================================================
# 接口:
# - POST /api/v1/contracts/{id}/analysis   触发合同分析(需 JWT)
# - GET  /api/v1/contracts/{id}/fields      获取合同字段(需 JWT)
#
# 另:GET /api/v1/analysis/{task_id} 在 api/analysis/routes.py 单独注册
#
# 职责:
# - 参数接收与校验
# - 调用 analysis_service
# - 返回统一 Response
#
# 禁止:
# - API 层直接调用 Pipeline / LLM / OCR
# - API 层直接访问数据库
from app.services import analysis_service


@contract_api_bp.route('/<int:contract_id>/analysis', methods=['POST'])
@jwt_required()
def trigger_contract_analysis(contract_id):
    """
    触发合同 AI 分析(需 JWT)

    流程:
    1. 创建 AnalysisTask(pending)
    2. 创建 Document(若不存在)
    3. 同步执行 Document Pipeline(extract → ocr → clean → chunk → llm → save)
    4. 返回任务结果(含 stages_log 进度)

    权限:
    - admin / contract_manager:可分析任意合同
    - employee:仅可分析自己的合同(他人合同返回 404)

    响应:
    - data.task:任务信息(含 status / current_stage / stages_log / error_message)
    - data.contract.analysis_status:回写后的合同分析状态(pending/processing/completed/failed)

    注意:本接口同步执行 Pipeline,耗时可能较长(10–60s);
         前端应设较长超时并展示 loading + 进度。
    """
    current_user = _get_current_user()
    task = analysis_service.trigger_analysis(contract_id, current_user)

    # 同步刷新合同 analysis_status 返回给前端
    contract = contract_service.get_contract_detail(contract_id, current_user)
    return success(
        data={'task': task, 'contract': contract},
        message='分析任务已完成' if task.get('status') == 'success' else '分析任务执行完毕(请查看状态)'
    )


@contract_api_bp.route('/<int:contract_id>/fields', methods=['GET'])
@jwt_required()
def get_contract_fields(contract_id):
    """
    获取合同字段(需 JWT)

    读取顺序:
    1. 优先读 contract_fields 表(最新成功任务的字段)
    2. 降级读 contracts.analysis_result(Sprint 2 旧合同)
    3. 都没有则返回空

    权限:
    - admin / contract_manager:可见任意合同字段
    - employee:仅可见自己合同字段(他人合同返回 404)

    响应:
    - data.fields:字段列表 [{field_name, field_label, field_value, confidence, source_text}]
    - data.task:最近任务信息 {id, task_no, status}(可能为 null)
    - data.source:数据来源 'contract_fields' / 'legacy_json' / 'empty'
    """
    current_user = _get_current_user()
    result = analysis_service.get_contract_fields(contract_id, current_user)
    return success(data=result)


# ============================================================
# Sprint 5 - v0.7.0:Contract Review Agent 审核接口
# ============================================================
# 接口:
# - POST /api/v1/contracts/{id}/review    触发合同 AI 风险审核(需 admin/contract_manager)
# - GET  /api/v1/contracts/{id}/reviews   合同的审核历史(需 JWT)
#
# 另:GET /api/v1/reviews/{id} 在 api/review/routes.py 单独注册
#
# 职责:
# - 参数接收与校验
# - 调用 review_service
# - 返回统一 Response
#
# 禁止:
# - API 层直接调用 Agent / LLM / Retriever
# - API 层直接访问数据库
# - API 层写业务逻辑(均下沉至 review_service)
from app.services import review_service


@contract_api_bp.route('/<int:contract_id>/review', methods=['POST'])
@role_required('admin', 'contract_manager')
def trigger_contract_review(contract_id):
    """
    触发合同 AI 风险审核(需 admin / contract_manager 角色)

    流程:
    1. 校验合同存在 + 权限(employee 由 @role_required 拦截,无法进入)
    2. 前置校验:合同需已完成 AI 分析(analysis_status=completed)
    3. 读取合同字段 + 合同全文
    4. 创建 ReviewReport(pending)
    5. 同步执行 Contract Review Agent(ReAct 循环:LLM 决策 + Tool 执行)
    6. 落库 risks / risk_level / summary / tool_calls_log
    7. 返回审核报告 + 合同信息

    权限:
    - admin / contract_manager:可审核任意合同
    - employee:无权触发(@role_required 拦截,返回 403)

    响应:
    - data.review:审核报告(含 risks / tool_calls_log / risk_level)
    - data.contract:合同信息(同步刷新状态)

    注意:
    - 本接口同步执行 Agent(LLM 多轮 + RAG 检索),耗时 15–90s;前端应设较长超时(300s)
    - Agent 失败(如 LLM 不可用)≠ 接口失败:ReviewReport 标记 failed 但仍落库,接口返回 200
    - 同合同可多次审核,每次创建新 ReviewReport
    """
    current_user = _get_current_user()
    review = review_service.trigger_review(contract_id, current_user)

    # 同步刷新合同信息返回给前端
    contract = contract_service.get_contract_detail(contract_id, current_user)
    return success(
        data={'review': review, 'contract': contract},
        message='审核任务已完成' if review.get('status') == 'success' else '审核任务执行完毕(请查看状态)'
    )


@contract_api_bp.route('/<int:contract_id>/reviews', methods=['GET'])
@jwt_required()
def list_contract_reviews(contract_id):
    """
    合同的审核历史(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见任意合同审核历史
    - employee:仅可见自己合同的审核历史(他人合同返回 404)

    响应:
    - data.items:审核列表(不含 risks 详情,仅摘要)
      [{id, review_no, status, risk_level, iterations, created_time, ...}]
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    current_user = _get_current_user()
    result = review_service.list_contract_reviews(
        contract_id, current_user, page=page, size=size
    )
    return success(data=result)
