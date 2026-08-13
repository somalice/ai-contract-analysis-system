"""
角色控制装饰器(Sprint 1 - v0.3.0)

用法:
    @role_required("admin")
    @role_required("admin", "contract_manager")

设计:
- 基于 JWT claims 中的 role 字段校验
- 依赖 @jwt_required(已内置)
- 不符合角色 → 抛 AuthError(403),由全局 ErrorHandler 统一返回

约束:
- 仅做角色校验(Authentication 层面),非完整 RBAC
- 不涉及部门/权限表/菜单
"""
from functools import wraps
from flask_jwt_extended import jwt_required, get_jwt
from app.utils.exceptions import AuthError


def role_required(*roles):
    """
    角色校验装饰器
    :param roles: 允许的角色列表,如 ("admin",) 或 ("admin", "contract_manager")
    """
    if not roles:
        raise ValueError('role_required 至少指定一个角色')

    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role')
            if user_role not in roles:
                raise AuthError(f'权限不足,需要角色: {", ".join(roles)}', code=403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator
