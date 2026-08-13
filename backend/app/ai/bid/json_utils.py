"""
JSON 解析工具(Sprint 7 - v0.9.0 / Sprint 8.6 统一)

职责:
- 从 LLM 输出中提取 JSON 对象(容错)
- 供 requirement_extractor 与 proposal_agent 复用(避免重复实现)

Sprint 8.6 变更:
- 实现已迁移至 app.ai.utils.json_repair(统一规范入口)
- 本模块保留为向后兼容的重新导出层(proposal_agent / requirement_extractor
  现有 `from app.ai.bid.json_utils import extract_json` 无需修改)
- 行为 100% 兼容,无破坏性变更
"""
# 重新导出统一实现(Sprint 8.6)
from app.ai.utils.json_repair import extract_json

__all__ = ['extract_json']
