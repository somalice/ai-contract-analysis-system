"""
认证业务服务(Sprint 1 - v0.3.0)

职责:
- 用户注册(校验 username 唯一、role 合法、密码 hash 保存)
- 用户登录(校验密码、生成 JWT access_token)
- 获取当前用户信息

约束:
- 本层不直接渲染模板、不访问 request 对象;参数由 API 层传入
- JWT 生成使用 flask_jwt_extended.create_access_token
- 所有异常抛出 AppException 子类(ValidationError/AuthError/BusinessError),由全局处理器统一返回

调用链:api/auth/routes.py → auth_service → models/user.py + extensions/jwt
"""
from flask_jwt_extended import create_access_token
from app.extensions.db import db
from app.extensions.logger import logger
from app.models.user import User
from app.utils.exceptions import ValidationError, AuthError


def register(username, password, role='employee'):
    """
    用户注册
    :param username: 用户名
    :param password: 明文密码(由 API 层接收,本层 hash 后存储)
    :param role: 角色(admin / contract_manager / employee)
    :return: dict 用户信息(不含 password_hash)
    """
    # ---------- 参数校验 ----------
    if not username or not username.strip():
        raise ValidationError('用户名不能为空')
    if not password:
        raise ValidationError('密码不能为空')
    if len(password) < 6:
        raise ValidationError('密码长度不能少于 6 位')
    username = username.strip()
    if len(username) > 64:
        raise ValidationError('用户名长度不能超过 64 字符')
    if len(password) > 128:
        raise ValidationError('密码长度不能超过 128 字符')
    if role not in User.VALID_ROLES:
        raise ValidationError(f'角色非法,允许: {", ".join(User.VALID_ROLES)}')

    # ---------- 唯一性校验 ----------
    existing = User.query.filter_by(username=username).first()
    if existing:
        raise ValidationError('用户名已存在')

    # ---------- 创建用户 ----------
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info('用户注册成功: id=%s username=%s role=%s', user.id, user.username, user.role)
    return user.to_dict()


def login(username, password):
    """
    用户登录
    :param username: 用户名
    :param password: 明文密码
    :return: dict {access_token, user}
    """
    if not username or not password:
        raise ValidationError('用户名和密码不能为空')

    user = User.query.filter_by(username=username.strip()).first()
    # 用户不存在或密码错误统一返回(避免泄露用户是否存在)
    if not user or not user.check_password(password):
        logger.warning('登录失败(用户名或密码错误): username=%s', username)
        raise AuthError('用户名或密码错误', code=401)

    # ---------- 生成 JWT ----------
    # identity 用 user_id(字符串);role 通过 additional_claims 携带,供 role_required 校验
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={'role': user.role, 'username': user.username}
    )

    logger.info('用户登录成功: id=%s username=%s role=%s', user.id, user.username, user.role)
    return {
        'access_token': access_token,
        'user': user.to_dict(),
    }


def get_user_by_id(user_id):
    """
    根据 ID 获取用户信息(用于 profile 接口)
    :param user_id: 用户 ID
    :return: dict 用户信息
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise ValidationError('用户 ID 非法')

    user = db.session.get(User, uid)
    if not user:
        from app.utils.exceptions import NotFoundError
        raise NotFoundError('用户不存在')

    return user.to_dict()
