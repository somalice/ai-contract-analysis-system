"""
Contract Generation Agent 模块(Sprint 6 - v0.8.0)

职责:
- 提供 AI 合同自动生成能力(模板变量 + RAG 检索 + AI 条款补充 + 规则校验)
- 手写 ReAct 循环(不引入 LangGraph / Agent 框架),复用 Sprint 5 Agent 思想

模块结构:
- context.py              GenerationContext(承载数据,不含业务逻辑)
- generation_agent.py     GenerationAgent(ReAct 循环主体)
- result.py               GenerationResult(Agent 产物)
- word_renderer.py        Word 渲染(docxtpl + python-docx)
- prompts/                Agent Prompt(版本化)
- tools/                  4 个 Tool(模板查询 / RAG 检索复用 / 条款生成 / 规则校验)

复用(只读 import,不修改 Sprint 5 核心逻辑):
- BaseTool / ToolRegistry  → app.ai.agent.tools.base / app.ai.agent.tool_registry
- call_deepseek            → app.ai.agent.llm_client(3-tuple 返回 + 错误分类)
- _safe_serialize          → app.ai.agent.context(Trace observation 安全序列化)
- KnowledgeSearchTool      → app.ai.agent.tools.knowledge_search_tool(直接注册到 Generation Agent)

调用链:
api/generation/routes.py(POST /generation/generate)
  → services/generation_service
    → GenerationAgent.run()
      → llm_client(DeepSeek 决策)
      → tools/*(执行)
    → word_renderer(渲染 Word)
    → models/generated_contract

约束:
- Agent 不直接访问数据库(通过 Tool)
- Tool 无状态、独立可测
- LLM 仅负责决策与条款生成,规则校验用确定性代码
- 禁止 print() / return str(e)
- 不修改 Sprint 3 Pipeline / Sprint 4 Knowledge Layer / Sprint 5 Review Agent 核心逻辑
"""
from app.ai.generation.context import GenerationContext
from app.ai.generation.result import GenerationResult
from app.ai.generation.generation_agent import GenerationAgent

__all__ = [
    'GenerationContext',
    'GenerationResult',
    'GenerationAgent',
]
