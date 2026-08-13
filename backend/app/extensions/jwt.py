"""
JWT 扩展实例(Sprint 1 - v0.3.0)

职责:
- 声明 Flask-JWT-Extended 实例(避免循环导入)
- 在 create_app() 中通过 jwt.init_app(app) 初始化
- 注册 JWT 异常回调,统一返回 {code, message, data} 格式

JWT 配置(JWT_SECRET_KEY 等)在 config/settings.py 中,从 .env 读取。
"""
from flask_jwt_extended import JWTManager

# 全局唯一 jwt 实例(在 create_app 中 init_app)
jwt = JWTManager()


def init_jwt(app):
    """
    初始化 JWT 扩展并注册异常回调。
    在 create_app() 中调用(在 db.init_app 之后)。

    所有 JWT 异常统一返回 {code, message, data} 格式,并记录日志。
    """
    from app.extensions.logger import logger
    from app.utils.response import error

    jwt.init_app(app)

    # ---------- JWT 异常统一回调 ----------

    @jwt.unauthorized_loader
    def missing_token_callback(reason):
        logger.warning('JWT 未提供: %s', reason)
        return error('未提供认证凭证', code=401)

    @jwt.invalid_token_loader
    def invalid_token_callback(reason):
        logger.warning('JWT 无效: %s', reason)
        return error('无效的认证凭证', code=401)

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        logger.warning('JWT 已过期: payload=%s', jwt_payload)
        return error('认证凭证已过期,请重新登录', code=401)

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        logger.warning('JWT 已撤销: payload=%s', jwt_payload)
        return error('认证凭证已失效', code=401)

    @jwt.needs_fresh_token_loader
    def needs_fresh_token_callback(jwt_header, jwt_payload):
        logger.warning('JWT 需要刷新: payload=%s', jwt_payload)
        return error('需要重新认证', code=401)
