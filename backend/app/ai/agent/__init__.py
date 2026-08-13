"""
Contract Review Agent 模块(Sprint 5 - v0.7.0)

职责:
- 提供 AI 合同风险审核能力(LLM 决策 + Tool 执行)
- 手写 ReAct 循环(不引入 LangGraph / Agent 框架)

模块结构:
- context.py              AgentContext(承载数据,不含业务逻辑)
- base.py                 BaseAgent ABC + AgentResult
- contract_review_agent.py ContractReviewAgent(ReAct 循环主体)
- tool_registry.py        ToolRegistry(注册 / 获取 Tool)
- llm_client.py           DeepSeek 调用封装(复用 ChatOpenAI 模式)
- prompts/                Agent Prompt(版本化)
- tools/                  3 个 Tool(字段查询 / RAG 检索 / 规则检查)

调用链:
api/contract/routes.py(POST /contracts/{id}/review)
  → services/review_service
    → ContractReviewAgent.run()
      → llm_client(DeepSeek 决策)
      → tools/*(执行)
    → models/review_report

约束:
- Agent 不直接访问数据库(通过 Tool)
- Tool 无状态、独立可测
- LLM 仅负责决策,规则检查用确定性代码
- 禁止 print() / return str(e)
"""
from app.ai.agent.context import AgentContext
from app.ai.agent.base import BaseAgent, AgentResult
from app.ai.agent.contract_review_agent import ContractReviewAgent
from app.ai.agent.tool_registry import ToolRegistry

__all__ = [
    'AgentContext',
    'BaseAgent',
    'AgentResult',
    'ContractReviewAgent',
    'ToolRegistry',
]
