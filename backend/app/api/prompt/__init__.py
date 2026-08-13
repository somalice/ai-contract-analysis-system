"""Prompt 蓝图初始化(Sprint 8 新增)"""
from flask import Blueprint

prompt_bp = Blueprint('prompt_api', __name__, url_prefix='/api/v1/prompts')

from . import routes  # noqa: F401 注册路由
