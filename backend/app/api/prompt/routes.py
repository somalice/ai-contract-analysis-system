"""
Prompt 模板管理 API(Sprint 8 - v1.0.0 企业级 AI 增强)

权限:
- GET 列表/详情: admin / contract_manager
- 创建/更新/激活/删除:仅 admin
"""
from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.api.prompt import prompt_bp
from app.decorators.role_required import role_required
from app.services import prompt_service
from app.utils import response
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError


@prompt_bp.route('', methods=['GET'])
@jwt_required()
@role_required('admin', 'contract_manager')
def list_templates():
    """GET /api/v1/prompts?name=&status=&page=1&size=20"""
    name = request.args.get('name')
    status = request.args.get('status')
    page = request.args.get('page', 1)
    size = request.args.get('size', 20)
    try:
        data = prompt_service.list_templates(name=name, status=status, page=page, size=size)
    except ValidationError as e:
        return response.error(str(e), 400)
    return response.success(data)


@prompt_bp.route('/<int:prompt_id>', methods=['GET'])
@jwt_required()
@role_required('admin', 'contract_manager')
def get_template(prompt_id):
    current_user = get_jwt_identity() or {}
    try:
        data = prompt_service.get_template(prompt_id, current_user=current_user)
    except NotFoundError as e:
        return response.error(str(e), 404)
    except ValidationError as e:
        return response.error(str(e), 400)
    return response.success(data)


@prompt_bp.route('', methods=['POST'])
@jwt_required()
@role_required('admin')
def create_template():
    current_user = get_jwt_identity() or {}
    user_id = current_user.get('id') if isinstance(current_user, dict) else None
    payload = request.get_json(silent=True) or {}
    required = ('name', 'version', 'system_prompt', 'human_prompt')
    missing = [k for k in required if not payload.get(k)]
    if missing:
        return response.error(f'缺少必填字段: {", ".join(missing)}', 400)
    try:
        data = prompt_service.create_template(
            name=payload['name'],
            version=str(payload['version']),
            system_prompt=payload['system_prompt'],
            human_prompt=payload['human_prompt'],
            description=payload.get('description'),
            status=payload.get('status', 'draft'),
            created_by=user_id,
        )
    except (ValidationError, BusinessError) as e:
        return response.error(str(e), 400)
    return response.success(data, '创建成功', 201)


@prompt_bp.route('/<int:prompt_id>', methods=['PUT'])
@jwt_required()
@role_required('admin')
def update_template(prompt_id):
    current_user = get_jwt_identity() or {}
    payload = request.get_json(silent=True) or {}
    allowed = ('system_prompt', 'human_prompt', 'description', 'status', 'version')
    update_kwargs = {k: payload[k] for k in allowed if k in payload}
    try:
        data = prompt_service.update_template(prompt_id, current_user, **update_kwargs)
    except NotFoundError as e:
        return response.error(str(e), 404)
    except (ValidationError, BusinessError) as e:
        return response.error(str(e), 400)
    return response.success(data, '更新成功')


@prompt_bp.route('/<int:prompt_id>/activate', methods=['POST'])
@jwt_required()
@role_required('admin')
def activate_template(prompt_id):
    """激活指定版本为 active(同 name 其他版本自动 inactive)"""
    current_user = get_jwt_identity() or {}
    try:
        data = prompt_service.activate_template(prompt_id, current_user)
    except NotFoundError as e:
        return response.error(str(e), 404)
    except (ValidationError, BusinessError) as e:
        return response.error(str(e), 400)
    return response.success(data, '已激活')


@prompt_bp.route('/<int:prompt_id>', methods=['DELETE'])
@jwt_required()
@role_required('admin')
def delete_template(prompt_id):
    current_user = get_jwt_identity() or {}
    try:
        data = prompt_service.delete_template(prompt_id, current_user)
    except NotFoundError as e:
        return response.error(str(e), 404)
    except BusinessError as e:
        return response.error(str(e), 400)
    return response.success(data, '删除成功')
