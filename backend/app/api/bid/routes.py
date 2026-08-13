"""
招标与投标管理 API(Blueprint)- Sprint 7.1 v0.9.1 增强

接口:

招标文件模块(前缀 /api/v1/bids,bid_bp):
- POST   /api/v1/bids/upload            上传招标文件(需 JWT,自动同步解析)
- GET    /api/v1/bids                   招标文件分页列表(需 JWT)
- GET    /api/v1/bids/<id>             招标文件详情(需 JWT,可选 include_text)
- DELETE /api/v1/bids/<id>             删除招标文件(需 admin / contract_manager)
- POST   /api/v1/bids/<id>/parse       重新解析招标文件(需 JWT,v0.9.1: version++,status=draft)
- GET    /api/v1/bids/<id>/requirement 查询招标需求 15 字段(需 JWT,v0.9.1:含 version/field_sources)
- POST   /api/v1/bids/<id>/generate    生成投标文件(需 JWT,v0.9.1:仅 status=approved 可生成)

---- Sprint 7.1 新增 Requirement Review 接口 ----
- PUT    /api/v1/bids/<id>/requirement/status            更新需求状态(通用于状态机)
- POST   /api/v1/bids/<id>/requirement/submit-review     提交审核 draft→reviewing
- POST   /api/v1/bids/<id>/requirement/review            审核通过/驳回 reviewing→approved/draft

投标生成模块(前缀 /api/v1/proposals,proposal_bp):
- GET    /api/v1/proposals              投标生成记录分页列表(需 JWT)
- GET    /api/v1/proposals/<id>         生成记录详情(含 sections/trace,v0.9.1 含 tool_stats)
- GET    /api/v1/proposals/<id>/trace   生成记录 Agent Trace(v0.9.1 含 tool_breakdown)
- GET    /api/v1/proposals/<id>/download 下载生成的 Word 文档(需 JWT)

Sprint 7.1 增强点:
1. Requirement Review: draft/reviewing/approved 三态审核流
2. Requirement Version:每次解析 version 自增(v1.0→v1.1)
3. Requirement Trace: field_sources(page_number/chunk_id/confidence/source_text)
4. Bid References:章节级 top_reference(document_id/chunk_id/page_number/similarity_score)
5. Tool Statistics:tool_call_count/success_rate/3 项 Duration/tool_breakdown
"""
from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import bid_service, proposal_service
from app.utils.response import success
from app.utils.exceptions import ValidationError
from app.decorators.role_required import role_required


# ============================================================
# 招标文件 Blueprint(前缀 /api/v1/bids)
# ============================================================
bid_bp = Blueprint('bid', __name__)


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


# ---------- 上传招标文件 ----------
@bid_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_bid_document():
    """
    上传招标文件(需 JWT)

    流程:
    1. 保存文件到 uploads/bids/{uuid}.ext
    2. 落库 BidDocument(parse_status=pending)
    3. 同步执行 Bid Pipeline(PDF/OCR → 文本清洗 → LLM 提取 15 字段)
    4. 落库 BidRequirement(1:1)
    5. 回写 parse_status=success / failed

    请求:multipart/form-data
      - file: 招标文件(必填,pdf/png/jpg/jpeg)
      - title: 招标标题(可选,默认取文件名去扩展名)

    响应:
    - data: 招标文件信息(含 requirement 概要 / parse_status)
      - parse_status=success:解析成功,可基于此生成投标
      - parse_status=failed:解析失败(LLM 不可用 / OCR 失败),可调用 /parse 重试

    注意:
    - 本接口同步执行 Pipeline,耗时 5-30s;前端应设较长超时(120s)
    - Pipeline 失败不报错,返回 parse_status=failed,前端可重试
    """
    file = request.files.get('file')
    if not file or not file.filename:
        raise ValidationError('请选择招标文件')

    title = request.form.get('title') or None

    current_user = _get_current_user()
    result = bid_service.upload_bid_document(
        file=file,
        current_user=current_user,
        title=title,
    )
    return success(
        data=result,
        message='招标文件上传成功,需求解析完成'
                if result.get('parse_status') == 'success'
                else '招标文件已上传,但需求解析失败,可重新解析',
    )


# ---------- 招标文件列表 ----------
@bid_bp.route('', methods=['GET'])
@jwt_required()
def list_bid_documents():
    """
    招标文件分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - parse_status: 解析状态过滤(pending / processing / success / failed,可选)
      - keyword: 关键字(title / bid_no 模糊搜索)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见全部招标文件
    - employee:仅可见自己上传的

    响应:
    - data.items:招标文件列表(含 requirement 概要,不含全文)
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    parse_status = request.args.get('status') or None
    keyword = request.args.get('keyword') or None

    current_user = _get_current_user()
    result = bid_service.list_bid_documents(
        current_user=current_user,
        page=page, size=size, parse_status=parse_status, keyword=keyword,
    )
    return success(data=result)


# ---------- 招标文件详情 ----------
@bid_bp.route('/<int:bid_document_id>', methods=['GET'])
@jwt_required()
def get_bid_document_detail(bid_document_id):
    """
    招标文件详情(需 JWT)

    查询参数:
      - include_text: 是否返回 text_content 全文(默认 false;true 时返回全文)

    权限:
    - admin / contract_manager:可见任意
    - employee:仅可见自己上传的(他人返回 404)

    响应:
    - data: 招标文件信息(含 requirement 概要;include_text=true 时含全文)
    """
    include_text = request.args.get('include_text', 'false').lower() == 'true'

    current_user = _get_current_user()
    result = bid_service.get_bid_document_detail(
        bid_document_id=bid_document_id,
        current_user=current_user,
        include_text=include_text,
    )
    return success(data=result)


# ---------- 删除招标文件 ----------
@bid_bp.route('/<int:bid_document_id>', methods=['DELETE'])
@role_required('admin', 'contract_manager')
def delete_bid_document(bid_document_id):
    """
    删除招标文件(需 admin / contract_manager)

    流程:
    1. 校验存在 + 权限
    2. 校验无关联的 GeneratedProposal(若有,提示先删除生成记录)
    3. 删除 BidDocument(cascade 删除 BidRequirement)
    4. 物理删除文件

    权限:
    - admin / contract_manager:可删除任意招标文件
    - employee:403(由 @role_required 拦截)

    响应:
    - data: {id, bid_no, status='deleted'}
    """
    current_user = _get_current_user()
    result = bid_service.delete_bid_document(
        bid_document_id=bid_document_id,
        current_user=current_user,
    )
    return success(data=result, message='招标文件已删除')


# ---------- 重新解析招标文件 ----------
@bid_bp.route('/<int:bid_document_id>/parse', methods=['POST'])
@jwt_required()
def parse_bid_document(bid_document_id):
    """
    重新解析招标文件(需 JWT)

    场景:首次解析失败(LLM 不可用 / OCR 失败)后,LLM 恢复时重试

    流程:
    1. 调用 run_bid_pipeline(复用已落库文件)
    2. UPSERT BidRequirement(1:1,UPDATE 原行)
    3. 回写 BidDocument(parse_status / text_content / extract_method)

    权限:
    - admin / contract_manager:可重新解析任意招标文件
    - employee:仅可重新解析自己上传的(他人 404)

    响应:
    - data: 更新后的招标文件信息(含 requirement 概要 / parse_status)
    """
    current_user = _get_current_user()
    result = bid_service.parse_bid_document(
        bid_document_id=bid_document_id,
        current_user=current_user,
    )
    return success(
        data=result,
        message='招标文件解析完成'
                if result.get('parse_status') == 'success'
                else '招标文件解析失败,请稍后重试',
    )


# ---------- 查询招标需求 ----------
@bid_bp.route('/<int:bid_document_id>/requirement', methods=['GET'])
@jwt_required()
def get_bid_requirement(bid_document_id):
    """
    查询招标需求 15 字段(需 JWT)

    返回结构化 Requirement:
    - project_name(项目名称)
    - tender_org(招标单位)
    - project_location(项目地点)
    - budget(预算)
    - deadline(投标截止时间)
    - duration(工期 / 服务期)
    - delivery_requirements(供货范围)
    - technical_requirements[](技术要求)
    - qualification_requirements[](资格要求)
    - scoring_criteria[](评分标准)
    - bid_opening_time(开标时间)
    - bid_validity(投标有效期)
    - payment_terms(付款条件)
    - contact(联系人)
    - other(其他)
    - confidence(LLM 自评置信度)

    权限:
    - admin / contract_manager:可见任意
    - employee:仅可见自己上传的招标文件的需求(他人 404)

    响应:
    - data: 招标需求信息(含 requirement_data 15 字段 + 质量指标)
    """
    current_user = _get_current_user()
    result = bid_service.get_bid_requirement(
        bid_document_id=bid_document_id,
        current_user=current_user,
    )
    return success(data=result)


# ---------- Sprint 7.1 新增:提交需求审核(draft→reviewing) ----------
@bid_bp.route('/<int:bid_document_id>/requirement/submit-review', methods=['POST'])
@jwt_required()
def submit_requirement_review(bid_document_id):
    """
    提交需求审核(Sprint 7.1): draft → reviewing

    场景:草稿态需求提交给管理员审核
    权限:
    - admin / contract_manager:任意提交
    - employee:仅可提交自己上传的招标文件的需求
    """
    current_user = _get_current_user()
    result = bid_service.submit_requirement_for_review(
        bid_document_id=bid_document_id,
        current_user=current_user,
    )
    return success(data=result, message='需求已提交审核')


# ---------- Sprint 7.1 新增:审核需求(通过/驳回) ----------
@bid_bp.route('/<int:bid_document_id>/requirement/review', methods=['POST'])
@role_required('admin', 'contract_manager')
def review_requirement(bid_document_id):
    """
    审核需求(Sprint 7.1): reviewing → approved / draft

    请求体(JSON):
      - approved: bool(true=通过, false=驳回)
      - comment:  string(驳回原因,可选)

    权限:admin / contract_manager
    """
    body = request.get_json(silent=True) or {}
    approved = bool(body.get('approved'))
    comment = body.get('comment') or None

    current_user = _get_current_user()
    result = bid_service.review_requirement(
        bid_document_id=bid_document_id,
        current_user=current_user,
        approved=approved,
        comment=comment,
    )
    return success(
        data=result,
        message='需求审核通过' if approved else (
            f'需求已驳回: {comment}' if comment else '需求已驳回,请修改后重新提交'
        ),
    )


# ---------- Sprint 7.1 新增:通用需求状态更新接口 ----------
@bid_bp.route('/<int:bid_document_id>/requirement/status', methods=['PUT'])
@jwt_required()
def update_requirement_status(bid_document_id):
    """
    通用需求状态更新(Sprint 7.1)
    等价于 submit-review + review 的合一入口,严格按状态机流转。

    请求体(JSON):
      - new_status: string(draft / reviewing / approved)
    """
    body = request.get_json(silent=True) or {}
    new_status = (body.get('new_status') or '').strip()
    if not new_status:
        raise ValidationError('参数 new_status 不能为空')

    current_user = _get_current_user()
    result = bid_service.update_requirement_status(
        bid_document_id=bid_document_id,
        current_user=current_user,
        new_status=new_status,
    )
    return success(data=result, message=f'需求状态已更新为 {new_status}')


# ---------- 生成投标文件 ----------
@bid_bp.route('/<int:bid_document_id>/generate', methods=['POST'])
@jwt_required()
def generate_proposal(bid_document_id):
    """
    生成投标文件(需 JWT)

    流程:
    1. 加载招标文件 + 需求 + 企业资料(knowledge_type='company')
    2. 同步执行 Proposal Agent(ReAct 循环,5 个 Tool)
    3. 渲染 Word 文件(docxtpl + python-docx,复用 Sprint 6)
    4. 落库 GeneratedProposal + ProposalSections(单事务)

    请求体:application/json(可选)
      {
        "input_data": {
          "company_profile_overrides": {...},
          "options": {...}
        }
      }

    响应:
    - data.proposal:生成记录(含 generated_sections / rag_references /
                      validation_results / agent_trace / trace_summary / file_info)

    注意:
    - 本接口同步执行 Agent + Word 渲染,耗时 15-90s;前端应设较长超时(300s)
    - Agent 失败(LLM 不可用)走兜底,仍渲染 Word(无 AI 章节骨架),接口不失败
    - 招标文件需 parse_status=success 才能生成
    """
    data = request.get_json(silent=True) or {}
    input_data = data.get('input_data')

    current_user = _get_current_user()
    result = proposal_service.generate_proposal(
        bid_document_id=bid_document_id,
        current_user=current_user,
        input_data=input_data,
    )
    return success(
        data=result,
        message='投标文件生成成功' if result.get('proposal', {}).get('status') == 'success'
                else '生成任务执行完毕(请查看状态)',
    )


# ============================================================
# 投标生成 Blueprint(前缀 /api/v1/proposals)
# ============================================================
proposal_bp = Blueprint('proposal', __name__)


# ---------- 生成记录列表 ----------
@proposal_bp.route('', methods=['GET'])
@jwt_required()
def list_proposals():
    """
    投标生成记录分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - status: 状态过滤(pending / running / success / failed,可选)
      - bid_document_id: 招标文件过滤(可选)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见全部生成记录
    - employee:仅可见自己触发的生成记录

    响应:
    - data.items:生成记录列表(含招标文件摘要,不含 sections / trace)
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    status = request.args.get('status') or None
    bid_document_id = request.args.get('bid_document_id') or None

    current_user = _get_current_user()
    result = proposal_service.list_proposals(
        current_user=current_user,
        page=page, size=size, status=status, bid_document_id=bid_document_id,
    )
    return success(data=result)


# ---------- 生成记录详情 ----------
@proposal_bp.route('/<int:proposal_id>', methods=['GET'])
@jwt_required()
def get_proposal(proposal_id):
    """
    生成记录详情(需 JWT)

    返回:
    - data.proposal:生成记录信息
      - id / proposal_no / bid_document_id / status
      - input_data
      - generated_sections: AI 生成章节 [{section_type, section_name, content, source, references}]
      - rag_references: RAG 命中规范
      - validation_results: 规则校验结果
      - agent_trace: Agent 执行 Trace
      - trace_summary: Trace 汇总
      - iterations / llm_error / error_message
      - file_info: {name, size}
      - bid 摘要
      - started_time / finished_time / created_time

    权限:
    - admin / contract_manager:可查任意生成记录
    - employee:仅可查自己触发的生成记录(他人返回 404)
    """
    current_user = _get_current_user()
    proposal = proposal_service.get_proposal(proposal_id, current_user)
    return success(data={'proposal': proposal})


# ---------- 生成记录 Agent Trace ----------
@proposal_bp.route('/<int:proposal_id>/trace', methods=['GET'])
@jwt_required()
def get_proposal_trace(proposal_id):
    """
    生成记录 Agent Trace(需 JWT)

    供前端 ProposalDetail 页 Agent 执行过程 Timeline 展示:
      - Thought → Decision → Action → Observation → Duration → Status

    返回:
    - data.trace:Agent 执行 Trace 摘要
      - id / proposal_no / bid_document_id / status / iterations
      - agent_trace:每步 {step, thought, decision, action, tool_name,
                          tool_input, observation, start_time, end_time,
                          duration_ms, status, error_message}
      - trace_summary:{steps, total_duration_ms, llm_duration_ms,
                       tool_duration_ms, tool_stats, llm_stats,
                       iterations, max_iterations, iteration_exceeded}
      - llm_error / llm_error_type
      - started_time / finished_time

    权限:
    - admin / contract_manager:可查任意生成记录
    - employee:仅可查自己触发的生成记录(他人返回 404)
    """
    current_user = _get_current_user()
    trace = proposal_service.get_proposal_trace(proposal_id, current_user)
    return success(data={'trace': trace})


# ---------- 下载投标文件 ----------
@proposal_bp.route('/<int:proposal_id>/download', methods=['GET'])
@jwt_required()
def download_proposal(proposal_id):
    """
    下载生成的投标 Word 文档(需 JWT)

    流程:
    1. 校验生成记录存在 + 权限(employee 仅可下载自己触发的)
    2. 校验 status=success(失败记录无文件)
    3. 校验文件物理存在
    4. 返回 Word 文件(send_file,as_attachment)

    响应:Word 文件下载流(Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document)

    权限:
    - admin / contract_manager:可下载任意生成文件
    - employee:仅可下载自己触发的生成文件
    """
    current_user = _get_current_user()
    proposal, file_path, download_name = proposal_service.get_proposal_file_path(
        proposal_id, current_user
    )
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
