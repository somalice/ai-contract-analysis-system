"""
Agent 执行上下文(Sprint 5 - v0.7.0 / v0.7.1 增强)

职责:
- 作为 Agent 与 Tool 之间数据传递的载体(借鉴 Sprint 3 PipelineContext 模式)
- 承载合同信息 / 字段 / 全文 / 工具调用轨迹 / Agent Trace / 最终产物
- 不包含业务逻辑,仅承载数据

设计原则(遵循 user_rules §9 Tool Design Rules / §10 Workflow):
- Tool 之间无直接依赖,仅通过 Context 共享数据
- Context 不包含业务逻辑
- Tool 只读 ctx 输入字段,写自己的产物字段

v0.7.1 增强(Sprint 5 Final):
- 新增 agent_trace 列表(结构化 Trace,每步含 thought/decision/action/observation/duration/status)
- 新增 Tool 调用统计(tool_call_count / tool_success_count / tool_failed_count)
- 新增 LLM 调用统计(llm_call_count / llm_total_ms / llm_error)
- 保持 tool_calls_log / observations 向后兼容
"""
from datetime import datetime
from typing import Any, Optional


class AgentContext:
    """
    Contract Review Agent 执行上下文

    生命周期:由 review_service 创建 → 传给 ContractReviewAgent → 传给各 Tool → 最终落库

    字段说明:
    - contract_id:审核的合同 ID
    - contract:合同基本信息 dict(Contract.to_dict())
    - fields:预读的 8 字段列表(供 LLM 初始参考 + risk_rule_tool)
    - document_text:合同全文(供 risk_rule_tool 关键条款检查)
    - task_id:关联的分析任务 ID(基于哪次分析的字段,null=无分析)
    - tool_calls_log:工具调用轨迹(审计用,落库到 review_reports.tool_calls_log)
    - agent_trace:Agent 执行 Trace(每步 thought/decision/action/observation,落库到 review_reports.agent_trace)
    - observations:LLM 对话历史(ReAct 循环用,内存,不落库)
    - iterations / max_iterations:迭代计数与上限(防无限循环)
    - risks / risk_level / summary:Agent 最终产物
    - tool_stats:Tool 调用聚合统计(次数 / 成功 / 失败)
    - llm_stats:LLM 调用聚合统计(次数 / 总耗时 / 错误)
    """

    def __init__(self, contract_id: int, contract: dict,
                 fields: list, document_text: str = '',
                 task_id: Optional[int] = None,
                 max_iterations: int = 5):
        # ---------- 输入 ----------
        self.contract_id: int = contract_id
        self.contract: dict = contract or {}
        self.fields: list = fields or []          # [{field_name, field_label, field_value, confidence, source_text}]
        self.document_text: str = document_text or ''
        self.task_id: Optional[int] = task_id
        self.max_iterations: int = max_iterations

        # ---------- 工具调用轨迹(审计,向后兼容) ----------
        # [{tool, args, duration_ms, result_summary, error}]
        self.tool_calls_log: list[dict] = []

        # ---------- Agent Trace(v0.7.1 新增,结构化执行过程) ----------
        # [{step, thought, decision, action, tool_name, tool_input, observation,
        #   start_time, end_time, duration_ms, status, error_message}]
        self.agent_trace: list[dict] = []

        # ---------- LLM 对话历史(ReAct 循环用,内存,不落库) ----------
        # 每轮追加 tool_result,供下一轮 LLM 参考
        self.observations: list[dict] = []  # [{tool, result}]

        # ---------- 控制 ----------
        self.iterations: int = 0

        # ---------- 产物 ----------
        self.risks: list[dict] = []
        self.risk_level: str = 'none'  # high / medium / low / none
        self.summary: str = ''

        # ---------- Tool 聚合统计(v0.7.1 新增) ----------
        # {tool_name: {call_count, success_count, failed_count, total_ms, last_error}}
        self.tool_stats: dict[str, dict] = {}

        # ---------- LLM 聚合统计(v0.7.1 新增) ----------
        # {call_count, total_ms, error}
        self.llm_stats: dict = {
            'call_count': 0,
            'total_ms': 0,
            'error': None,
        }

    # ============================================================
    # Trace 录制(v0.7.1 新增)
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

        :param thought: LLM 思考内容(这一步想做什么)
        :param decision: 决策理由(为什么选择这个 Tool / 为什么输出最终报告)
        :param action: 动作类型(call_tool / final_report / llm_call / system / iteration_exceeded)
        :param tool_name: Tool 名称(action=call_tool 时填)
        :param tool_input: Tool 输入参数
        :param observation: 观察结果(Tool 返回摘要 / LLM 响应摘要)
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
    # 工具调用日志(向后兼容)
    # ============================================================
    def add_tool_call(self, tool_name: str, args: dict,
                      duration_ms: int, result_summary: str,
                      error: Optional[str] = None) -> None:
        """
        追加一条工具调用日志(向后兼容 v0.7.0)
        :param tool_name: Tool 名称
        :param args: 调用参数
        :param duration_ms: 执行耗时(毫秒)
        :param result_summary: 结果摘要(便于审计,不存完整结果)
        :param error: 失败原因(成功时为 None)
        """
        self.tool_calls_log.append({
            'tool': tool_name,
            'args': args,
            'duration_ms': duration_ms,
            'result_summary': result_summary,
            'error': error,
        })
        # 同步更新 Tool 聚合统计(v0.7.1 新增)
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
        """
        追加一条工具观察结果(供下一轮 LLM Prompt 使用)
        :param tool_name: Tool 名称
        :param result: Tool 返回的结构化结果(序列化为 JSON 字符串喂给 LLM)
        """
        self.observations.append({'tool': tool_name, 'result': result})

    # ============================================================
    # LLM 统计(v0.7.1 新增)
    # ============================================================
    def add_llm_call(self, duration_ms: int, error: Optional[str] = None) -> None:
        """记录一次 LLM 调用"""
        self.llm_stats['call_count'] += 1
        self.llm_stats['total_ms'] += duration_ms
        if error:
            self.llm_stats['error'] = error

    # ============================================================
    # Trace 汇总(v0.7.1 新增,供 API 返回)
    # ============================================================
    def get_trace_summary(self) -> dict:
        """
        生成 Trace 汇总(供 GET /reviews/{id}/trace 接口)

        :return: {steps, total_duration_ms, llm_duration_ms, tool_duration_ms,
                  tool_stats, llm_stats, iteration_exceeded}
        """
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
            f'<AgentContext contract_id={self.contract_id} '
            f'fields={len(self.fields)} text_len={len(self.document_text)} '
            f'iterations={self.iterations}/{self.max_iterations} '
            f'tool_calls={len(self.tool_calls_log)} '
            f'trace_steps={len(self.agent_trace)}>'
        )


def _safe_serialize(obj: Any, max_len: int = 500) -> Any:
    """
    安全序列化 observation(截断过长内容,确保可 JSON 序列化)

    处理策略:
    - str:截断过长内容
    - dict:递归序列化(处理嵌套 datetime / Exception)
    - list:递归序列化 + 长度限制
    - datetime:转为 ISO 字符串(确保 JSON 可序列化)
    - Exception:转为字符串
    - Decimal / int / float / bool / None:原样返回
    - 其他对象:转为字符串兜底
    """
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj[:max_len] + '...(截断)' if len(obj) > max_len else obj
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%dT%H:%M:%S.%f')
    if isinstance(obj, Exception):
        return f'{type(obj).__name__}: {str(obj)}'
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_serialize(v, max_len) for v in obj[:20]]
    if isinstance(obj, tuple):
        return [_safe_serialize(v, max_len) for v in obj[:20]]
    # 兜底:转字符串,防止自定义对象导致 JSON 序列化失败
    return str(obj)[:max_len]
