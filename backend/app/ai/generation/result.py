"""
Generation Agent 执行结果(Sprint 6 - v0.8.0)

职责:
- 承载 GenerationAgent.run() 的产物:补充条款 / RAG 引用 / 校验结果 / Trace

设计:
- 与 Sprint 5 AgentResult 同形(status / iterations / llm_error / llm_error_type /
  tool_calls_log / agent_trace / trace_summary),便于前端复用 Timeline
- 生成专属字段:generated_clauses / rag_references / validation_results
- 不修改 Sprint 5 AgentResult(领域不同,独立类)
"""
from typing import Optional


class GenerationResult:
    """Generation Agent 执行结果"""

    # 状态枚举(与 GeneratedContract 状态机一致)
    SUCCESS = 'success'
    FAILED = 'failed'

    def __init__(self, status: str,
                 generated_clauses: Optional[list] = None,
                 rag_references: Optional[list] = None,
                 validation_results: Optional[dict] = None,
                 summary: str = '',
                 iterations: int = 0,
                 error: Optional[str] = None,
                 llm_error: Optional[str] = None,
                 llm_error_type: Optional[str] = None,
                 tool_calls_log: Optional[list] = None,
                 agent_trace: Optional[list] = None,
                 trace_summary: Optional[dict] = None):
        """
        :param status: success / failed
        :param generated_clauses: AI 补充条款 [{name, content, source, references}]
        :param rag_references: RAG 命中规范(复用 Sprint 4 references 结构)
        :param validation_results: 规则校验结果 {passed, issues}
        :param summary: 生成总结
        :param iterations: Agent 迭代次数
        :param error: 整体失败原因(成功为 None)
        :param llm_error: LLM 失败原因(成功为 None)
        :param llm_error_type: LLM 错误分类(复用 Sprint 5 枚举)
        :param tool_calls_log: 工具调用轨迹
        :param agent_trace: Agent 执行 Trace
        :param trace_summary: Trace 汇总统计
        """
        self.status = status
        self.generated_clauses = generated_clauses or []
        self.rag_references = rag_references or []
        self.validation_results = validation_results or {'passed': True, 'issues': []}
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

    def __repr__(self) -> str:
        return (
            f'<GenerationResult {self.status} clauses={len(self.generated_clauses)} '
            f'refs={len(self.rag_references)} iterations={self.iterations} '
            f'trace_steps={len(self.agent_trace)}>'
        )
