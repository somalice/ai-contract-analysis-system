"""
统一 API 响应工具(Sprint 0 Release Check - P3)

遵循 API_DESIGN.md 统一返回格式:
- 成功:{"code":200,"message":"success","data":{}}
- 失败:{"code":4xx/5xx,"message":"...","data":null}

仅用于 JSON API 接口(health、未来 auth 等)。
合同上传页(/)为 HTML 模板渲染,不在本工具范围内,保持原有 render_template 行为。
"""
from flask import jsonify


def success(data=None, message='success', code=200):
    """
    成功响应
    :param data: 业务数据(默认 {} 或传入对象)
    :param message: 提示信息(默认 success)
    :param code: 业务码(默认 200)
    """
    payload = data if data is not None else {}
    return jsonify({'code': code, 'message': message, 'data': payload}), code


def error(message, code=400, data=None):
    """
    失败响应
    :param message: 错误信息
    :param code: HTTP/业务码(4xx/5xx,默认 400)
    :param data: 附加数据(默认 null)
    """
    return jsonify({'code': code, 'message': message, 'data': data}), code
