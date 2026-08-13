"""
Agent Tool 模块(Sprint 5 - v0.7.0)

3 个 Tool:
- contract_field_tool    查询合同结构化字段(复用 analysis_service)
- knowledge_search_tool  RAG 检索(复用 Sprint 4 retriever)
- risk_rule_tool         规则化风险检查(确定性代码,不调 LLM)
"""
from app.ai.agent.tools.base import BaseTool
from app.ai.agent.tools.contract_field_tool import ContractFieldTool
from app.ai.agent.tools.knowledge_search_tool import KnowledgeSearchTool
from app.ai.agent.tools.risk_rule_tool import RiskRuleTool

__all__ = [
    'BaseTool',
    'ContractFieldTool',
    'KnowledgeSearchTool',
    'RiskRuleTool',
]
