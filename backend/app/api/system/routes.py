"""
系统模块 API(Blueprint)

提供系统级接口(健康检查等),统一使用 JSON 响应格式。
路径前缀:/api/v1(在 create_app 中通过 url_prefix 注册)
"""
from flask import Blueprint
from app.utils.response import success

system_bp = Blueprint('system', __name__)


@system_bp.route('/health', methods=['GET'])
def health():
    """
    健康检查接口
    不依赖数据库、不依赖 DeepSeek,仅用于系统运行检测。
    返回:{"code":200,"message":"success","data":{"status":"ok"}}
    """
    return success(data={'status': 'ok'})
