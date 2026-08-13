"""
Generation Agent 执行上下文(Sprint 6 - v0.8.0)

职责:
- 作为 Generation Agent 与 Tool 之间数据传递的载体(借鉴 Sprint 5 AgentContext 模式)
- 承载模板信息 / 用户变量 / AI 补充条款 / RAG 引用 / 校验结果 / Trace
- 不包含业务逻辑,仅承载数据

设计原则(遵循 user_rules §9 Tool Design Rules / §10 Workflow):
- Tool 之间无直接依赖,仅通过 Context 共享数据
- Context 不包含业务逻辑
- Tool 只读 ctx 输入字段,写自己的产物字段

复用 Sprint 5(只读 import,不修改):
- _safe_serialize:Trace observation 安全序列化(模块级函数,直接 import)

与 Sprint 5 AgentContext 的区别:
- AgentContext 为审核专属(contract_id / fields / document_text / risks)
- GenerationContext 为生成专属(template / input_variables / generated_clauses / validation_results)
- Trace 机制(tool_calls_log / agent_trace / tool_stats / llm_stats)同形,便于前端复用 Timeline
"""
from datetime import datetime
from typing import Any, Optional

# 复用 Sprint 5 的安全序列化工具(模块级函数,只读 import,不修改 Sprint 5)
from app.ai.agent.context import _safe_serialize


class GenerationContext:
    """
    Contract Generation Agent 执行上下文

    生命周期:由 generation_service 创建 → 传给 GenerationAgent → 传给各 Tool → 最终落库

    字段说明:
    - template:模板信息 dict(ContractTemplate.to_dict(),含 variables)
    - input_variables:用户填写的变量键值 {var_name: value}
    - contract_type:合同类型(供 RAG 检索与 LLM 决策)
    - generated_clauses:AI 补充条款 [{name, content, source, references}]
    - rag_references:RAG 命中规范(累积,复用 Sprint 4 references 结构)
    - validation_results:规则校验结果 {passed, issues:[{type, description, suggestion}]}
    - tool_calls_log:工具调用轨迹(审计用,落库到 generated_contracts.tool_calls_log)
    - agent_trace:Agent 执行 Trace(落库到 generated_contracts.agent_trace)
    - observations:LLM 对话历史(ReAct 循环用,内存,不落库)
    - iterations / max_iterations:迭代计数与上限(防无限循环)
    - tool_stats:Tool 调用聚合统计
    - llm_stats:LLM 调用聚合统计
    """

    def __init__(self, template: dict, input_variables: dict,
                 contract_type: str = '', max_iterations: int = 5):
        # ---------- 输入 ----------
        self.template: dict = template or {}
        self.input_variables: dict = input_variables or {}
        self.contract_type: str = contract_type or ''
        self.max_iterations: int = max_iterations

        # ---------- 工具调用轨迹(审计) ----------
        self.tool_calls_log: list[dict] = []

        # ---------- Agent Trace(结构化执行过程) ----------
        self.agent_trace: list[dict] = []

        # ---------- LLM 对话历史(ReAct 循环用,内存) ----------
        self.observations: list[dict] = []

        # ---------- 控制 ----------
        self.iterations: int = 0

        # ---------- 产物 ----------
        self.generated_clauses: list[dict] = []
        self.rag_references: list[dict] = []
        self.validation_results: dict = {'passed': True, 'issues': []}

        # ---------- Tool 聚合统计 ----------
        self.tool_stats: dict[str, dict] = {}

        # ---------- LLM 聚合统计 ----------
        self.llm_stats: dict = {
            'call_count': 0,
            'total_ms': 0,
            'error': None,
        }

    # ============================================================
    # Trace 录制(与 Sprint 5 AgentContext 同形,便于前端复用 Timeline)
    # ============================================================
    def add_trace_step(self, thought: str = '', decision: str = '',
                       action: str = '', tool_name: str = '',
                       tool_input: Optional[dict] = None,
                       observation: Any = None,
                       start_time: Optional[str] = None,
                       end_time: Optional[str] = None,
                       duration_ms: int = 0,
                       status: str = 'success',
                       error_message: Optional[str] = None) -> int:
        """
        追加一条 Agent Trace 步骤

        :param thought: LLM 思考内容
        :param decision: 决策理由
        :param action: 动作类型(call_tool / final_report / llm_call / system / iteration_exceeded / fallback)
        :param tool_name: Tool 名称(action=call_tool 时填)
        :param tool_input: Tool 输入参数
        :param observation: 观察结果
        :param start_time: 开始时间(ISO 字符串)
        :param end_time: 结束时间(ISO 字符串)
        :param duration_ms: 耗时(毫秒)
        :param status: 状态(success / failed / skipped)
        :param error_message: 错误信息(失败时填)
        :return: step 序号(从 1 开始)
        """
        step = len(self.agent_trace) + 1
        self.agent_trace.append({
            'step': step,
            'thought': thought or '',
            'decision': decision or '',
            'action': action or '',
            'tool_name': tool_name or '',
            'tool_input': tool_input or {},
            'observation': _safe_serialize(observation),
            'start_time': start_time or '',
            'end_time': end_time or '',
            'duration_ms': duration_ms,
            'status': status or 'success',
            'error_message': error_message or '',
        })
        return step

    # ============================================================
    # 工具调用日志
    # ============================================================
    def add_tool_call(self, tool_name: str, args: dict,
                      duration_ms: int, result_summary: str,
                      error: Optional[str] = None) -> None:
        """追加一条工具调用日志"""
        self.tool_calls_log.append({
            'tool': tool_name,
            'args': args,
            'duration_ms': duration_ms,
            'result_summary': result_summary,
            'error': error,
        })
        self._update_tool_stats(tool_name, duration_ms, error is None, error)

    def _update_tool_stats(self, tool_name: str, duration_ms: int,
                           success: bool, error: Optional[str]) -> None:
        """更新 Tool 聚合统计"""
        if tool_name not in self.tool_stats:
            self.tool_stats[tool_name] = {
                'call_count': 0,
                'success_count': 0,
                'failed_count': 0,
                'total_ms': 0,
                'last_error': None,
            }
        stats = self.tool_stats[tool_name]
        stats['call_count'] += 1
        stats['total_ms'] += duration_ms
        if success:
            stats['success_count'] += 1
        else:
            stats['failed_count'] += 1
            stats['last_error'] = error

    def add_observation(self, tool_name: str, result: Any) -> None:
        """追加一条工具观察结果(供下一轮 LLM Prompt 使用)"""
        self.observations.append({'tool': tool_name, 'result': result})

    # ============================================================
    # 产物累积(供 Tool 回写)
    # ============================================================
    def add_generated_clause(self, name: str, content: str,
                             source: str = 'ai',
                             references: Optional[list] = None) -> None:
        """追加一条 AI 补充条款"""
        self.generated_clauses.append({
            'name': name,
            'content': content,
            'source': source,
            'references': references or [],
        })

    def add_rag_references(self, references: list) -> None:
        """累积 RAG 命中规范(去重,按 document_id + chunk_id 复合键,保持引用顺序)"""
        existing_keys = {
            (r.get('document_id'), r.get('chunk_id'))
            for r in self.rag_references
            if r.get('chunk_id') is not None
        }
        for ref in references or []:
            # chunk_id 为 None 时不参与去重(允许累积,避免丢失无 chunk_id 的引用)
            if ref.get('chunk_id') is None:
                self.rag_references.append(ref)
                continue
            key = (ref.get('document_id'), ref.get('chunk_id'))
            if key in existing_keys:
                continue
            self.rag_references.append(ref)
            existing_keys.add(key)

    def add_validation_issue(self, issue_type: str, description: str,
                             suggestion: str = '') -> None:
        """追加一条校验问题"""
        self.validation_results['issues'].append({
            'type': issue_type,
            'description': description,
            'suggestion': suggestion,
        })
        self.validation_results['passed'] = False

    # ============================================================
    # LLM 统计
    # ============================================================
    def add_llm_call(self, duration_ms: int, error: Optional[str] = None) -> None:
        """记录一次 LLM 调用"""
        self.llm_stats['call_count'] += 1
        self.llm_stats['total_ms'] += duration_ms
        if error:
            self.llm_stats['error'] = error

    # ============================================================
    # Trace 汇总
    # ============================================================
    def get_trace_summary(self) -> dict:
        """生成 Trace 汇总(供 API 返回)"""
        total_duration_ms = sum(s.get('duration_ms', 0) for s in self.agent_trace)
        llm_duration_ms = self.llm_stats.get('total_ms', 0)
        tool_duration_ms = sum(
            s.get('total_ms', 0) for s in self.tool_stats.values()
        )
        return {
            'steps': len(self.agent_trace),
            'total_duration_ms': total_duration_ms,
            'llm_duration_ms': llm_duration_ms,
            'tool_duration_ms': tool_duration_ms,
            'tool_stats': self.tool_stats,
            'llm_stats': self.llm_stats,
            'iterations': self.iterations,
            'max_iterations': self.max_iterations,
            'iteration_exceeded': self.iterations >= self.max_iterations,
        }

    def __repr__(self) -> str:
        return (
            f'<GenerationContext template_id={self.template.get("id")} '
            f'vars={len(self.input_variables)} clauses={len(self.generated_clauses)} '
            f'refs={len(self.rag_references)} '
            f'iterations={self.iterations}/{self.max_iterations} '
            f'tool_calls={len(self.tool_calls_log)} '
            f'trace_steps={len(self.agent_trace)}>'
        )
