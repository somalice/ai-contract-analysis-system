"""
Agent 抽象基类(Sprint 5 - v0.7.0 / v0.7.1 增强)

职责:
- 定义 Agent 统一契约:run(ctx) → AgentResult
- ContractReviewAgent 为具体实现(ReAct 循环)

设计原则(遵循 user_rules §8 Agent Design Rules):
- Agent 负责规划 / 决策 / 工具选择 / 工作流编排
- Agent 不负责 DB 操作(通过 Tool)
- Agent 不负责数据处理实现(通过 Tool)
- 避免 Universal Agent,每个 Agent 单一职责

借鉴 Sprint 3 BaseStage + runner 模式(Stage 由 runner 编排,Tool 由 Agent 编排)。

v0.7.1 增强(Sprint 5 Final):
- AgentResult 新增 agent_trace / trace_summary / llm_error_type 字段
- 支持 Trace 持久化与可观测
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.ai.agent.context import AgentContext


class AgentResult:
    """Agent 执行结果"""

    # 状态枚举(与 ReviewReport 状态机一致)
    SUCCESS = 'success'
    FAILED = 'failed'

    def __init__(self, status: str, risk_level: str = 'none',
                 risks: Optional[list] = None, summary: str = '',
                 iterations: int = 0, error: Optional[str] = None,
                 llm_error: Optional[str] = None,
                 llm_error_type: Optional[str] = None,
                 tool_calls_log: Optional[list] = None,
                 agent_trace: Optional[list] = None,
                 trace_summary: Optional[dict] = None):
        """
        :param status: success / failed
        :param risk_level: high / medium / low / none(失败时为 none)
        :param risks: 风险列表(结构见 SPRINT5_ANALYSIS §6.2)
        :param summary: 审核总结
        :param iterations: Agent 迭代次数
        :param error: 整体失败原因(成功时为 None)
        :param llm_error: LLM 失败原因(成功时为 None)
        :param llm_error_type: LLM 错误分类(timeout / rate_limit / server_error / network / auth / json_parse / unknown)
        :param tool_calls_log: 工具调用轨迹
        :param agent_trace: Agent 执行 Trace(v0.7.1 新增)
        :param trace_summary: Trace 汇总统计(v0.7.1 新增)
        """
        self.status = status
        self.risk_level = risk_level
        self.risks = risks or []
        self.summary = summary
        self.iterations = iterations
        self.error = error
        self.llm_error = llm_error
        self.llm_error_type = llm_error_type
        self.tool_calls_log = tool_calls_log or []
        self.agent_trace = agent_trace or []
        self.trace_summary = trace_summary or {}

    @property
    def is_success(self) -> bool:
        return self.status == self.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status == self.FAILED

    def to_dict(self) -> dict:
        """转为 dict(供 review_service 落库)"""
        return {
            'status': self.status,
            'risk_level': self.risk_level,
            'risks': self.risks,
            'summary': self.summary,
            'iterations': self.iterations,
            'error': self.error,
            'llm_error': self.llm_error,
            'llm_error_type': self.llm_error_type,
            'tool_calls_log': self.tool_calls_log,
            'agent_trace': self.agent_trace,
            'trace_summary': self.trace_summary,
        }

    def __repr__(self) -> str:
        return (
            f'<AgentResult {self.status} risk={self.risk_level} '
            f'risks={len(self.risks)} iterations={self.iterations} '
            f'trace_steps={len(self.agent_trace)}>'
        )


class BaseAgent(ABC):
    """Agent 抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent 名称"""

    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentResult:
        """
        执行 Agent(子类实现)
        :param ctx: AgentContext(已含输入数据)
        :return: AgentResult
        """
