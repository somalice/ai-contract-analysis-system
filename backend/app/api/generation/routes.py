"""
合同生成 API(Blueprint)- Sprint 6 v0.8.0

接口:
- POST /api/v1/generation/preview           预览生成结果(需 JWT,跑 Agent 但不渲染 Word)
- POST /api/v1/generation/generate          正式生成合同(需 JWT,跑 Agent + 渲染 Word + 建合同)
- GET  /api/v1/generation/history           生成记录分页列表(需 JWT)
- GET  /api/v1/generation/<id>              生成记录详情(含 clauses / trace,需 JWT)
- GET  /api/v1/generation/<id>/trace        生成记录 Agent Trace(需 JWT,供前端 Timeline)
- GET  /api/v1/generated/<id>/download      下载生成的 Word 文档(需 JWT)

职责:
- 参数接收与校验
- 调用 generation_service
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接调用 Agent / LLM / Word 渲染
- API 层写业务逻辑(均下沉至 generation_service)

权限:
- JWT 认证(全部接口需登录)
- 任意角色均可预览 / 生成(任务书要求"普通用户仅可使用模板",指使用权限)
- employee 仅可查询自己触发的生成记录(由 generation_service 过滤)
- 下载:employee 仅可下载自己触发的生成文件

约束:
- 不引入 Celery / Redis / LangGraph,Agent 同步执行
- Agent 失败(LLM 不可用)走兜底,仍渲染 Word(无 AI 条款),接口不失败
"""
import os
from flask import Blueprint, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import generation_service
from app.utils.response import success
from app.utils.exceptions import ValidationError

generation_bp = Blueprint('generation', __name__)


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


@generation_bp.route('/preview', methods=['POST'])
@jwt_required()
def preview_generation():
    """
    预览合同生成结果(需 JWT)

    流程:
    1. 加载并校验模板
    2. 校验输入变量
    3. 同步执行 Generation Agent(ReAct 循环)
    4. 返回预览结果(不渲染 Word,不建合同)

    请求体:application/json
      {
        "template_id": 1,
        "input_variables": {"party_a": "甲方公司", "amount": "100000"},
        "contract_type": "采购合同"  // 可选,默认取模板类型
      }

    响应:
    - data.generation:生成记录(含 generated_clauses / rag_references /
                      validation_results / agent_trace / trace_summary,
                      status=success 但 contract_id=null / file_info=null)
    """
    data = request.get_json(silent=True) or {}
    template_id = data.get('template_id')
    input_variables = data.get('input_variables')
    contract_type = data.get('contract_type') or None

    if not template_id:
        raise ValidationError('template_id 不能为空')

    current_user = _get_current_user()
    result = generation_service.preview_generation(
        template_id=template_id,
        input_variables=input_variables,
        current_user=current_user,
        contract_type=contract_type,
    )
    return success(data=result, message='预览生成完成')


@generation_bp.route('/generate', methods=['POST'])
@jwt_required()
def generate_contract():
    """
    正式生成合同(需 JWT)

    流程:
    1. 加载并校验模板
    2. 校验输入变量
    3. 同步执行 Generation Agent(ReAct 循环)
    4. 渲染 Word 文档(docxtpl)
    5. 创建合同记录(进入合同管理中心,可继续 Sprint 3 分析 / Sprint 5 审核)
    6. 落库生成结果

    请求体:application/json
      {
        "template_id": 1,
        "input_variables": {"party_a": "甲方公司", "amount": "100000"},
        "contract_type": "采购合同",  // 可选
        "title": "采购合同-2026年8月",  // 可选,默认取模板名 + 日期
        "description": "AI 自动生成"     // 可选
      }

    响应:
    - data.generation:生成记录(含 clauses / trace / contract 摘要 / file_info)
    - data.contract:新创建的合同信息(可在合同管理中心查看)

    注意:
    - 本接口同步执行 Agent + Word 渲染,耗时 15–90s;前端应设较长超时(300s)
    - Agent 失败(LLM 不可用)走兜底,仍渲染 Word + 建合同,接口不失败
    """
    data = request.get_json(silent=True) or {}
    template_id = data.get('template_id')
    input_variables = data.get('input_variables')
    contract_type = data.get('contract_type') or None
    title = data.get('title') or None
    description = data.get('description') or None

    if not template_id:
        raise ValidationError('template_id 不能为空')

    current_user = _get_current_user()
    result = generation_service.generate_contract(
        template_id=template_id,
        input_variables=input_variables,
        current_user=current_user,
        contract_type=contract_type,
        title=title,
        description=description,
    )
    return success(
        data=result,
        message='合同生成成功,已自动创建合同记录'
                if result.get('generation', {}).get('status') == 'success'
                else '生成任务执行完毕(请查看状态)',
    )


@generation_bp.route('/history', methods=['GET'])
@jwt_required()
def list_generations():
    """
    生成记录分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - status: 状态过滤(pending / running / success / failed,可选)
      - template_id: 模板过滤(可选)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见全部生成记录
    - employee:仅可见自己触发的生成记录

    响应:
    - data.items:生成记录列表(含模板摘要 + 合同摘要,不含 clauses / trace)
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    status = request.args.get('status') or None
    template_id = request.args.get('template_id') or None

    current_user = _get_current_user()
    result = generation_service.list_generations(
        current_user=current_user,
        page=page, size=size, status=status, template_id=template_id,
    )
    return success(data=result)


@generation_bp.route('/<int:generation_id>', methods=['GET'])
@jwt_required()
def get_generation(generation_id):
    """
    生成记录详情(需 JWT)

    返回:
    - data.generation:生成记录信息
      - id / generation_no / template_id / contract_id / status
      - input_variables
      - generated_clauses: AI 补充条款 [{name, content, source, references}]
      - rag_references: RAG 命中规范
      - validation_results: 规则校验结果
      - agent_trace: Agent 执行 Trace
      - trace_summary: Trace 汇总
      - iterations / llm_error / error_message
      - file_info: {name, size}
      - template / contract 摘要
      - started_time / finished_time / created_time

    权限:
    - admin / contract_manager:可查任意生成记录
    - employee:仅可查自己触发的生成记录(他人返回 404)
    """
    current_user = _get_current_user()
    generation = generation_service.get_generation(generation_id, current_user)
    return success(data={'generation': generation})


@generation_bp.route('/<int:generation_id>/trace', methods=['GET'])
@jwt_required()
def get_generation_trace(generation_id):
    """
    生成记录 Agent Trace(需 JWT)

    供前端 GenerationDetail 页 Agent 执行过程 Timeline 展示:
      - Thought → Decision → Action → Observation → Duration → Status

    返回:
    - data.trace:Agent 执行 Trace 摘要
      - id / generation_no / template_id / contract_id / status / iterations
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
    trace = generation_service.get_trace(generation_id, current_user)
    return success(data={'trace': trace})


# ============================================================
# 下载接口(独立路由,前缀 /api/v1/generated)
# ============================================================
# 注:此接口在 create_app 中通过独立 Blueprint 注册,前缀 /api/v1/generated
# 此处定义 download_generated_contract 函数,由 generated_download_bp 引用
generated_download_bp = Blueprint('generated_download', __name__)


@generated_download_bp.route('/<int:generation_id>/download', methods=['GET'])
@jwt_required()
def download_generated_contract(generation_id):
    """
    下载生成的合同 Word 文档(需 JWT)

    流程:
    1. 校验生成记录存在 + 权限(employee 仅可下载自己触发的)
    2. 校验 status=success(预览 / 失败记录无文件)
    3. 校验文件物理存在
    4. 返回 Word 文件(send_file,as_attachment)

    响应:Word 文件下载流(Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document)

    权限:
    - admin / contract_manager:可下载任意生成文件
    - employee:仅可下载自己触发的生成文件
    """
    current_user = _get_current_user()
    generation, file_path, download_name = generation_service.get_generated_file_path(
        generation_id, current_user
    )
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
