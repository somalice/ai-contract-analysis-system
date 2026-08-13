"""
合同模板管理 API(Blueprint)- Sprint 6 v0.8.0

接口:
- GET    /api/v1/templates                 模板分页列表(需 JWT)
- POST   /api/v1/templates/upload          上传模板(需 admin / contract_manager)
- GET    /api/v1/templates/<id>            模板详情(含 variables,需 JWT)
- PATCH  /api/v1/templates/<id>/status     启停模板(需 admin / contract_manager)
- DELETE /api/v1/templates/<id>            删除模板(需 admin / contract_manager)

职责:
- 参数接收与校验(file 存在性 / 文件名非空 / 类型允许 / 状态非空)
- 调用 template_service
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接调用 docxtpl / 解析变量
- API 层写业务逻辑(均下沉至 template_service)

权限:
- JWT 认证(全部接口需登录)
- 上传 / 启停 / 删除:仅 admin / contract_manager(@role_required 拦截 employee → 403)
- 列表 / 详情:employee 仅可见 active 模板(由 template_service 过滤)
"""
import os
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.services import template_service
from app.utils.response import success
from app.utils.exceptions import ValidationError
from app.decorators.role_required import role_required

template_bp = Blueprint('template', __name__)


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


@template_bp.route('', methods=['GET'])
@jwt_required()
def list_templates():
    """
    模板分页列表(需 JWT)

    查询参数:
      - page: 页码(默认 1)
      - size: 每页数量(默认 20,最大 100)
      - keyword: 关键字(name / template_no 模糊搜索)
      - status: 状态过滤(active / disabled,employee 强制 active)
      - contract_type: 合同类型过滤
      - version: 模板版本过滤(精确匹配,如 v1.0)

    排序:created_time DESC

    权限:
    - admin / contract_manager:可见全部模板(含 disabled)
    - employee:仅可见 active 模板(后端强制过滤)

    响应:
    - data.items:模板列表(不含 variables 详情,仅摘要)
    - data.total / data.page / data.size
    """
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    keyword = request.args.get('keyword') or None
    status = request.args.get('status') or None
    contract_type = request.args.get('contract_type') or None
    version = request.args.get('version') or None

    current_user = _get_current_user()
    result = template_service.get_template_list(
        page=page, size=size, keyword=keyword, status=status,
        contract_type=contract_type, version=version, current_user=current_user,
    )
    return success(data=result)


@template_bp.route('/upload', methods=['POST'])
@role_required('admin', 'contract_manager')
def upload_template():
    """
    上传模板(需 admin / contract_manager 角色)

    请求:multipart/form-data
      - file: 模板文件(必填,.docx)
      - name: 模板名称(可选,默认取文件名去扩展名)
      - description: 模板说明(可选)
      - contract_type: 合同类型(可选,默认"未分类")
      - version: 模板版本(可选,默认 v1.0;用于区分同名模板的不同迭代版本)

    流程:上传 .docx → 保存文件 → 解析 {{variable}} → 建模板记录(status=active)

    响应:
    - data.template:模板信息(含 variables)
    """
    if 'file' not in request.files:
        raise ValidationError('未选择模板文件')
    file = request.files['file']
    if not file.filename:
        raise ValidationError('文件名为空')

    name = request.form.get('name') or None
    description = request.form.get('description') or None
    contract_type = request.form.get('contract_type') or '未分类'
    version = request.form.get('version') or None

    current_user = _get_current_user()
    template = template_service.create_template(
        file, current_user,
        name=name, description=description,
        contract_type=contract_type, version=version,
    )
    return success(data={'template': template}, message='模板上传成功')


@template_bp.route('/<int:template_id>', methods=['GET'])
@jwt_required()
def get_template(template_id):
    """
    模板详情(需 JWT)

    返回:模板完整信息(含 variables)

    权限:
    - admin / contract_manager:可见任意模板
    - employee:仅可见 active 模板(disabled 返回 404 防枚举)
    """
    current_user = _get_current_user()
    template = template_service.get_template(template_id, current_user)
    return success(data={'template': template})


@template_bp.route('/<int:template_id>/status', methods=['PATCH'])
@role_required('admin', 'contract_manager')
def update_template_status(template_id):
    """
    启停模板(需 admin / contract_manager 角色)

    请求体:application/json
      { "status": "active" }  // active / disabled

    active ⇄ disabled 可反复切换(幂等)
    """
    data = request.get_json(silent=True) or {}
    target_status = data.get('status', '')
    if not target_status:
        raise ValidationError('状态不能为空')

    current_user = _get_current_user()
    template = template_service.update_template_status(
        template_id, target_status, current_user
    )
    return success(data={'template': template}, message='模板状态更新成功')


@template_bp.route('/<int:template_id>', methods=['DELETE'])
@role_required('admin', 'contract_manager')
def delete_template(template_id):
    """
    删除模板(需 admin / contract_manager 角色)

    约束:
    - 若模板已被用于生成(存在 generated_contracts 记录),禁止删除,提示"已有生成记录,建议停用"
    - 删除为硬删除(连同文件一起清理)

    响应:成功返回 data=null + message
    """
    current_user = _get_current_user()
    template_service.delete_template(template_id, current_user)
    return success(data=None, message='模板删除成功')
