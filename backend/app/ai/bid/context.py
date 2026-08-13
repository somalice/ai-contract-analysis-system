"""
Proposal Agent 执行上下文(Sprint 7.1 - v0.9.1 增强)

职责:
- 作为 Proposal Agent 与 Tool 之间数据传递的载体(镜像 Sprint 6 GenerationContext)
- 承载招标信息 / 需求 / 企业资料 / AI 生成章节 / RAG 引用 / 校验结果 / Trace

Sprint 7.1 新增:
- rag_context: Requirement Context Builder 预构建的 RAG Context
  (technical/qualification/case/company 四槽位,复用 Sprint 4 Retriever)
- add_trace_step 新增 type 字段:tool / llm / iteration / final / system
  (与 Sprint 5 Contract Review Agent Trace 统一格式)
- get_trace_summary 返回 Sprint 5 统一格式:tool_call_count / tool_success_rate /
  tool_duration_ms / llm_duration_ms / total_duration_ms / tool_breakdown
"""
from datetime import datetime
from typing import Any, Optional

# 复用 Sprint 5 的安全序列化工具(模块级函数,只读 import,不修改 Sprint 5)
from app.ai.agent.context import _safe_serialize


class ProposalContext:
    """
    Proposal Agent 执行上下文

    生命周期:由 proposal_service 创建 → 传给 ProposalAgent → 传给各 Tool → 最终落库

    字段说明:
    - bid_info:招标文件基本信息 dict(BidDocument.to_dict() 概要)
    - requirements:招标需求 15 字段 dict(供 requirement_tool / LLM 决策)
    - company_profile:企业资料 dict(预加载自 knowledge_type='company' 文档)
    - input_data:用户传入的 input 参数(company_profile_overrides / options)
    - generated_sections:AI 生成章节 [{section_type, section_name, content, source, references}]
    - rag_references:RAG 命中规范(累积,复用 Sprint 4 references 结构)
    - validation_results:规则校验结果 {passed, issues}
    - tool_calls_log:工具调用轨迹(审计用,落库到 generated_proposals)
    - agent_trace:Agent 执行 Trace(落库到 generated_proposals.agent_trace)
    - observations:LLM 对话历史(ReAct 循环用,内存,不落库)
    - iterations / max_iterations:迭代计数与上限(防无限循环)
    - tool_stats:Tool 调用聚合统计
    - llm_stats:LLM 调用聚合统计
    """

    def __init__(self, bid_info: dict, requirements: dict,
                 company_profile: dict, input_data: dict = None,
                 max_iterations: int = 5):
        # ---------- 输入 ----------
        self.bid_info: dict = bid_info or {}
        self.requirements: dict = requirements or {}
        self.company_profile: dict = company_profile or {}
        self.input_data: dict = input_data or {}
        self.max_iterations: int = max_iterations

        # ---- Sprint 7.1 新增:Requirement Context Builder 预构建 RAG Context ----
        # 结构见 context_builder.RequirementContextBuilder.build()
        self.rag_context: dict = {
            'technical': [], 'qualification': [], 'case': [], 'company': [],
            'query_terms': {'technical': [], 'qualification': [],
                             'case': [], 'company': []},
            'stats': {'retrieved_count': 0, 'slots_filled': 0, 'duration_ms': 0},
        }

        # ---------- 工具调用轨迹(审计) ----------
        self.tool_calls_log: list[dict] = []

        # ---------- Agent Trace(结构化执行过程) ----------
        self.agent_trace: list[dict] = []

        # ---------- LLM 对话历史(ReAct 循环用,内存) ----------
        self.observations: list[dict] = []

        # ---------- 控制 ----------
        self.iterations: int = 0

        # ---------- 产物 ----------
        self.generated_sections: list[dict] = []
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
    # Trace 录制(与 Sprint 5/6 同形,便于前端复用 Timeline)
    # ============================================================
    def add_trace_step(self, thought: str = '', decision: str = '',
                       action: str = '', tool_name: str = '',
                       tool_input: Optional[dict] = None,
                       observation: Any = None,
                       start_time: Optional[str] = None,
                       end_time: Optional[str] = None,
                       duration_ms: int = 0,
                       status: str = 'success',
                       error_message: Optional[str] = None,
                       step_type: str = '') -> int:
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
        :param step_type: Sprint 7.1 新增: step 类型(tool / llm / iteration / final / system)
                          用于 aggregate_tool_stats 聚合,与 Sprint 5 统一
        :return: step 序号(从 1 开始)
        """
        # ---- Sprint 7.1 step_type 推断(与 Sprint 5 统一格式) ----
        if not step_type:
            if tool_name:
                step_type = 'tool'
            elif action == 'final_report':
                step_type = 'final'
            elif action == 'llm_call':
                step_type = 'llm'
            elif action in ('system', 'iteration_exceeded', 'fallback'):
                step_type = action
            else:
                step_type = 'iteration'

        success = (status == 'success')
        step = len(self.agent_trace) + 1
        self.agent_trace.append({
            'step': step,
            'type': step_type,   # Sprint 7.1 新增 step 类型
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
            'success': success,        # Sprint 7.1 新增:bool,便于聚合
            'error': error_message or '',  # Sprint 7.1 新增:统一字段
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
    def add_generated_section(self, section_type: str, section_name: str,
                              content: str, source: str = 'ai',
                              references: Optional[list] = None) -> None:
        """追加一条 AI 生成章节(同 section_type 覆盖旧值)"""
        # 同类型章节覆盖(避免重复)
        self.generated_sections = [
            s for s in self.generated_sections
            if s.get('section_type') != section_type
        ]
        self.generated_sections.append({
            'section_type': section_type,
            'section_name': section_name,
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
            if ref.get('chunk_id') is None:
                self.rag_references.append(ref)
                continue
            key = (ref.get('document_id'), ref.get('chunk_id'))
            if key in existing_keys:
                continue
            self.rag_references.append(ref)
            existing_keys.add(key)

    def add_validation_issue(self, issue_type: str, description: str,
                             suggestion: str = '', severity: str = 'medium') -> None:
        """追加一条校验问题"""
        self.validation_results['issues'].append({
            'type': issue_type,
            'description': description,
            'suggestion': suggestion,
            'severity': severity,
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
        """
        生成 Trace 汇总(供 API 返回)
        Sprint 7.1 新增:返回 Sprint 5 统一格式的 Tool Statistics:
        - tool_call_count / tool_success_count / tool_failed_count
        - tool_success_rate / tool_duration_ms / llm_duration_ms / total_duration_ms
        - tool_breakdown
        """
        # ---- Sprint 7.1 Tool Statistics ----
        from app.services.proposal_service import aggregate_tool_stats
        total_dur_s = sum(s.get('duration_ms', 0) for s in self.agent_trace) / 1000.0
        stats = aggregate_tool_stats(
            agent_trace=self.agent_trace,
            trace_summary={'llm_calls': self.llm_stats.get('call_count', 0),
                           'llm_duration_ms': self.llm_stats.get('total_ms', 0)},
            total_duration_s=total_dur_s,
        )

        return {
            # ---- 基础计数 ----
            'steps': len(self.agent_trace),
            'iterations': self.iterations,
            'max_iterations': self.max_iterations,
            'iteration_exceeded': self.iterations >= self.max_iterations,
            # ---- Sprint 5 统一格式 Tool Statistics ----
            'tool_call_count': stats['tool_call_count'],
            'tool_success_count': stats['tool_success_count'],
            'tool_failed_count': stats['tool_failed_count'],
            'tool_success_rate': stats['tool_success_rate'],
            # ---- 时长(3 项统一可观测能力) ----
            'tool_duration_ms': stats['tool_duration_ms'],
            'llm_duration_ms': stats['llm_duration_ms'],
            'total_duration_ms': stats['total_duration_ms'],
            # ---- 明细 ----
            'tool_breakdown': stats['tool_breakdown'],
            'tool_stats': self.tool_stats,
            'llm_stats': self.llm_stats,
            # ---- Sprint 7.1 RAG Context 概要 ----
            'rag_context_stats': (self.rag_context or {}).get('stats', {}),
            'rag_slots_filled': (self.rag_context or {}).get('stats', {}).get('slots_filled', 0),
            'rag_documents_count': (self.rag_context or {}).get('stats', {}).get('retrieved_count', 0),
        }

    def __repr__(self) -> str:
        return (
            f'<ProposalContext bid_id={self.bid_info.get("id")} '
            f'requirements_fields={len(self.requirements)} '
            f'sections={len(self.generated_sections)} '
            f'refs={len(self.rag_references)} '
            f'iterations={self.iterations}/{self.max_iterations} '
            f'tool_calls={len(self.tool_calls_log)} '
            f'trace_steps={len(self.agent_trace)}>'
        )
