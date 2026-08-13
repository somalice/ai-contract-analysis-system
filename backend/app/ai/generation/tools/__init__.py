"""
Generation Agent Tool 模块(Sprint 6 - v0.8.1)

4 个 Tool:
- template_tool            查询模板变量清单与必填项(从 ctx 读,无参数)
- knowledge_search_tool    RAG 检索企业合同规范(复用 Sprint 5,直接 import)
- clause_generation_tool   调 LLM 生成指定类型条款文本(参数:clause_type/context)
- contract_rule_tool       合同规则校验:缺失字段 + 风险条款(确定性,不调 LLM)

复用 Sprint 5(只读 import,不修改):
- BaseTool                 → app.ai.agent.tools.base
- KnowledgeSearchTool      → app.ai.agent.tools.knowledge_search_tool(直接注册)
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.agent.tools.knowledge_search_tool import KnowledgeSearchTool  # 直接复用 Sprint 5
from app.ai.generation.tools.template_tool import TemplateTool
from app.ai.generation.tools.clause_generation_tool import ClauseGenerationTool
from app.ai.generation.tools.contract_rule_tool import ContractRuleTool

__all__ = [
    'BaseTool',
    'KnowledgeSearchTool',  # 复用 Sprint 5
    'TemplateTool',
    'ClauseGenerationTool',
    'ContractRuleTool',
]
