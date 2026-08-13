"""Evaluation 蓝图初始化(Sprint 8 新增)"""
from flask import Blueprint

evaluation_bp = Blueprint('evaluation_api', __name__, url_prefix='/api/v1/evaluation')

from . import routes  # noqa: F401
