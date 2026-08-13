"""
Tool 注册表(Sprint 5 - v0.7.0)

职责:
- 维护 Agent 可用的 Tool 实例
- 提供 register / get / list_for_prompt 接口
- list_for_prompt 生成工具描述(写进 Agent Prompt)

设计:
- Tool 实例无状态,可复用(单例即可)
- Agent 初始化时注册 3 个 Tool
"""
from app.extensions.logger import logger

from app.ai.agent.tools.base import BaseTool


class ToolRegistry:
    """Tool 注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册 Tool(按 name 索引)"""
        if not isinstance(tool, BaseTool):
            raise TypeError(f'注册对象必须是 BaseTool 子类: {type(tool)}')
        self._tools[tool.name] = tool
        logger.info('[Agent:registry] 注册 Tool: %s', tool.name)

    def get(self, name: str) -> BaseTool:
        """
        获取 Tool
        :raises KeyError: Tool 不存在
        """
        if name not in self._tools:
            raise KeyError(f'未注册的 Tool: {name}')
        return self._tools[name]

    def has(self, name: str) -> bool:
        """是否已注册"""
        return name in self._tools

    def list_for_prompt(self) -> list[dict]:
        """列出所有 Tool 的 Prompt 描述(供 Agent System Prompt)"""
        return [tool.to_prompt_dict() for tool in self._tools.values()]

    @property
    def size(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        names = list(self._tools.keys())
        return f'<ToolRegistry tools={names}>'
