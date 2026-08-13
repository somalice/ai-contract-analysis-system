"""
AI 工具包(Sprint 8.6 - v1.0.0)

职责:
- 提供 AI 层通用纯函数工具(无 Flask 依赖,便于跨模块复用与单元测试)

导出:
- extract_json: 从 LLM 输出中容错提取 JSON 对象
"""
from .json_repair import extract_json

__all__ = ['extract_json']
