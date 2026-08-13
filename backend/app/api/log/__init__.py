"""Logs 蓝图初始化(Sprint 8 新增:系统日志 API,对应 API_DESIGN §10)"""
from flask import Blueprint

log_bp = Blueprint('log_api', __name__, url_prefix='/api/v1/logs')

from . import routes  # noqa: F401 注册路由
