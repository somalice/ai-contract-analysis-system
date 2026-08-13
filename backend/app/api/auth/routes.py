"""
认证模块 API(Blueprint)- Sprint 1 v0.3.0

接口:
- POST /api/v1/auth/register  用户注册
- POST /api/v1/auth/login     用户登录
- GET  /api/v1/auth/profile    获取当前用户信息(需 JWT)

职责:
- 参数接收与校验(基本非空)
- 调用 auth_service
- 返回统一 Response

禁止:
- API 层直接访问数据库
- API 层直接生成 JWT
- API 层写业务逻辑(均下沉至 auth_service)
"""
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services import auth_service
from app.utils.response import success

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    role = data.get('role', 'employee')

    user = auth_service.register(username=username, password=password, role=role)
    return success(data={'user': user}, message='注册成功')


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')

    result = auth_service.login(username=username, password=password)
    return success(data=result, message='登录成功')


@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def profile():
    """获取当前用户信息(需 JWT)"""
    user_id = get_jwt_identity()
    user = auth_service.get_user_by_id(user_id)
    return success(data={'user': user}, message='success')
