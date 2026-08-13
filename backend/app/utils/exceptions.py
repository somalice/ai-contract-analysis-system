"""
统一异常体系(Sprint 0 Release Check - P4)

提供自定义业务异常基类 + 全局 ErrorHandler 注册。
所有未捕获异常返回统一 JSON,禁止 return str(e) / print(e) 后直接返回。

异常分级:
- AppException:业务异常基类(可预期,4xx)
- ValidationError:参数校验失败(400)
- BusinessError:业务规则违反(400/409)
- NotFoundError:资源不存在(404)
- AuthError:认证/授权失败(401/403)
- 内部异常(500):由 Flask 兜底 ErrorHandler 捕获
"""
from flask import jsonify


class AppException(Exception):
    """业务异常基类"""

    def __init__(self, message, code=400, error_code=None, data=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_code = error_code or code
        self.data = data


class ValidationError(AppException):
    """参数校验失败(400)"""

    def __init__(self, message='参数校验失败', data=None):
        super().__init__(message, code=400, error_code=400, data=data)


class BusinessError(AppException):
    """业务规则违反(400)"""

    def __init__(self, message='业务处理失败', data=None):
        super().__init__(message, code=400, error_code=400, data=data)


class NotFoundError(AppException):
    """资源不存在(404)"""

    def __init__(self, message='资源不存在', data=None):
        super().__init__(message, code=404, error_code=404, data=data)


class AuthError(AppException):
    """认证/授权失败(401)"""

    def __init__(self, message='认证失败', code=401, data=None):
        super().__init__(message, code=code, error_code=code, data=data)


def register_error_handlers(app):
    """
    注册全局错误处理器(在 create_app 中调用)
    统一返回 {"code","message","data"} 格式
    """
    from app.extensions.logger import logger

    @app.errorhandler(AppException)
    def handle_app_exception(e):
        logger.warning('业务异常: %s (code=%s)', e.message, e.code, exc_info=True)
        return jsonify({'code': e.code, 'message': e.message, 'data': e.data}), e.code

    @app.errorhandler(400)
    def handle_400(e):
        logger.warning('请求格式错误: %s', str(e))
        return jsonify({'code': 400, 'message': '请求格式错误', 'data': None}), 400

    @app.errorhandler(404)
    def handle_404(e):
        logger.warning('路由不存在: %s', str(e))
        return jsonify({'code': 404, 'message': '资源不存在', 'data': None}), 404

    @app.errorhandler(405)
    def handle_405(e):
        logger.warning('方法不允许: %s', str(e))
        return jsonify({'code': 405, 'message': '方法不允许', 'data': None}), 405

    @app.errorhandler(413)
    def handle_413(e):
        logger.warning('文件过大: %s', str(e))
        return jsonify({'code': 413, 'message': '上传文件过大', 'data': None}), 413

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception('服务器内部错误: %s', str(e))
        return jsonify({'code': 500, 'message': '服务器内部错误', 'data': None}), 500

    @app.errorhandler(Exception)
    def handle_unexpected(e):
        logger.exception('未捕获异常: %s', str(e))
        return jsonify({'code': 500, 'message': '服务器内部错误', 'data': None}), 500
