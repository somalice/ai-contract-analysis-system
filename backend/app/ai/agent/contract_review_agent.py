"""
Contract Review Agent(Sprint 5 - v0.7.0)

职责:
- ReAct 循环主体:LLM 决策 → Tool 执行 → 观察结果 → 再决策 → 最终报告
- 手写实现(不引入 LangGraph / Agent 框架)

执行流程:
1. 加载 Prompt(contract_review_v1.md)
2. 注册 3 个 Tool
3. ReAct 循环(最多 max_iterations 轮):
   a. 构建 Human Prompt(合同信息 + 字段 + 已有观察)
   b. 调用 DeepSeek
   c. 解析 JSON 决策
   d. call_tool → 执行 → 观察入 ctx → 继续
   e. final_report → 校验 → 返回
4. LLM 失败 / 达到迭代上限 → 兜底用 risk_rule_tool 生成报告

容错:
- LLM 不可用 / JSON 解析失败 → 兜底报告(规则风险)
- Tool 异常 → safe_run 返回 error dict,不中断循环
- 迭代上限 → 兜底报告

约束:
- 不直接访问数据库(通过 Tool)
- 不硬编码 Prompt(从 prompts/ 加载)
- 禁止 print() / return str(e)
"""
import json
import os
import re
from datetime import datetime
from typing import Optional

from app.extensions.logger import logger

from app.ai.agent.base import BaseAgent, AgentResult
from app.ai.agent.context import AgentContext
from app.ai.agent.llm_client import call_deepseek
from app.ai.agent.tool_registry import ToolRegistry
from app.ai.agent.tools import (
    ContractFieldTool,
    KnowledgeSearchTool,
    RiskRuleTool,
)
# Sprint 8.6: 统一 JSON 容错解析(原局部 _extract_json 已迁移至 json_repair)
from app.ai.utils.json_repair import extract_json as _extract_json


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'prompts', 'contract_review_v1.md'
)

# ---------- 严重度等级(用于 risk_level 计算) ----------
_SEVERITY_ORDER = {'high': 3, 'medium': 2, 'low': 1}
_VALID_RISK_LEVELS = ('high', 'medium', 'low', 'none')
_VALID_SEVERITIES = ('high', 'medium', 'low')


# ============================================================
# Prompt 加载与构建
# ============================================================
def _load_prompt():
    """
    Sprint 8 新增:DB active 模板优先,失败回退原文件解析逻辑。
    :return: (system_prompt, human_prompt_template)
    """
    # Sprint 8: DB active Prompt 优先(全程 try/except 保护,异常直接回退文件)
    try:
        from app.services import prompt_service
        tpl = prompt_service.get_active_template('contract_review')
        if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
            return tpl['system_prompt'], tpl['human_prompt']
    except Exception as _e:
        logger.warning('[Agent][Review] PromptTemplate DB 查询失败,回退原 .md 文件: %s', _e)

    # ---------- Sprint 0~7 原逻辑(100% 保留,作为 fallback)----------
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Agent] Prompt 文件加载失败: %s', _PROMPT_FILE)
        return (
            '你是合同风险审核 Agent。通过调用工具收集信息,输出严格 JSON 决策。'
            '动作:call_tool(调用工具)或 final_report(最终报告)。禁止编造。',
            '【合同信息】\n{contract_info}\n\n【字段】\n{fields_info}\n\n'
            '【观察】\n{observations}\n\n迭代:{iterations}/{max_iterations}'
        )

    system_prompt = ''
    human_prompt = ''
    current_section = None
    system_lines = []
    human_lines = []

    for line in content.split('\n'):
        if line.strip() == '## System Prompt':
            current_section = 'system'
            continue
        if line.strip() == '## Human Prompt':
            current_section = 'human'
            continue
        if line.strip().startswith('## ') and current_section:
            current_section = None
            continue
        if current_section == 'system':
            system_lines.append(line)
        elif current_section == 'human':
            human_lines.append(line)

    system_prompt = '\n'.join(system_lines).strip()
    human_prompt = '\n'.join(human_lines).strip()

    if not system_prompt:
        system_prompt = '你是合同风险审核 Agent,输出严格 JSON 决策。'
    if not human_prompt:
        human_prompt = '{contract_info}\n{fields_info}\n{observations}\n{iterations}/{max_iterations}'

    return system_prompt, human_prompt


def _format_contract_info(ctx: AgentContext) -> str:
    """格式化合同基本信息(供 Prompt)"""
    c = ctx.contract or {}
    lines = [
        f"合同ID:{ctx.contract_id}",
        f"合同编号:{c.get('contract_no', '未知')}",
        f"合同标题:{c.get('title', '未知')}",
        f"合同类型:{c.get('contract_type', '未分类')}",
        f"合同状态:{c.get('status', '未知')}",
    ]
    return '\n'.join(lines)


def _format_fields_info(ctx: AgentContext) -> str:
    """格式化已提取的字段(供 Prompt)"""
    if not ctx.fields:
        return '(暂无字段,可调用 contract_field_tool 查询)'
    lines = []
    for f in ctx.fields:
        name = f.get('field_label') or f.get('field_name', '?')
        val = f.get('field_value')
        conf = f.get('confidence', 0)
        val_str = val if val else '(缺失)'
        lines.append(f"- {name}:{val_str}(置信度:{conf})")
    return '\n'.join(lines)


def _format_observations(ctx: AgentContext) -> str:
    """格式化已收集的工具观察结果(供 Prompt)"""
    if not ctx.observations:
        return '(尚未调用任何工具,建议先调用 risk_rule_tool)'
    parts = []
    for i, obs in enumerate(ctx.observations, 1):
        tool = obs.get('tool', '?')
        result = obs.get('result', {})
        # 截断过长的 result,控制 token
        result_str = json.dumps(result, ensure_ascii=False)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + '...(截断)'
        parts.append(f'[{i}] 工具 {tool} 返回:\n{result_str}')
    return '\n\n'.join(parts)


def _build_human_prompt(ctx: AgentContext, system_prompt: str, human_template: str) -> str:
    """构建 Human Prompt(填充占位符)"""
    return human_template.format(
        contract_info=_format_contract_info(ctx),
        fields_info=_format_fields_info(ctx),
        observations=_format_observations(ctx),
        iterations=ctx.iterations,
        max_iterations=ctx.max_iterations,
    )


# ============================================================
# JSON 解析(容错)
# Sprint 8.6: _extract_json 已迁移至 app.ai.utils.json_repair,顶部 import as _extract_json
# ============================================================


# ============================================================
# risk_level 计算
# ============================================================
def _compute_risk_level(risks: list) -> str:
    """根据 risks 列表计算整体风险等级(取最高 severity)"""
    if not risks:
        return 'none'
    max_level = 0
    for r in risks:
        sev = r.get('severity', 'low')
        if sev in _SEVERITY_ORDER:
            max_level = max(max_level, _SEVERITY_ORDER[sev])
    if max_level >= 3:
        return 'high'
    if max_level == 2:
        return 'medium'
    if max_level == 1:
        return 'low'
    return 'none'


def _normalize_risk(risk: dict) -> dict:
    """规范化单条风险结构(确保字段齐全)"""
    return {
        'type': risk.get('type', '其他'),
        'severity': risk.get('severity', 'low') if risk.get('severity') in _VALID_SEVERITIES else 'low',
        'description': risk.get('description', ''),
        'suggestion': risk.get('suggestion', ''),
        'evidence': risk.get('evidence', ''),
        'references': risk.get('references', []) or [],
    }


# ============================================================
# ContractReviewAgent
# ============================================================
class ContractReviewAgent(BaseAgent):
    """合同审核 Agent(ReAct 循环)"""

    def __init__(self, max_iterations: int = None):
        """
        :param max_iterations: ReAct 最大迭代次数(None 时从 config 读取,默认 5)
        """
        # v0.7.1: 从 config 读取 MAX_AGENT_ITERATIONS(默认 5)
        if max_iterations is None:
            try:
                from flask import current_app
                max_iterations = current_app.config.get('MAX_AGENT_ITERATIONS', 5)
            except RuntimeError:
                max_iterations = 5  # 非 Flask 上下文(单元测试)时回退默认值
        self.max_iterations = max_iterations
        self._system_prompt, self._human_template = _load_prompt()
        self._registry = ToolRegistry()
        self._register_default_tools()

    @property
    def name(self) -> str:
        return 'contract_review_agent'

    def _register_default_tools(self):
        """注册 3 个默认 Tool"""
        self._registry.register(ContractFieldTool())
        self._registry.register(KnowledgeSearchTool())
        self._registry.register(RiskRuleTool())

    # ---------- Tool 执行 ----------
    def _execute_tool(self, tool_name: str, args: dict,
                      thought: str, decision: str,
                      ctx: AgentContext) -> dict:
        """
        执行 Tool 并记录日志 + 观察 + Trace
        :param tool_name: Tool 名称
        :param args: Tool 参数
        :param thought: LLM 的思考(来自 decision JSON)
        :param decision: LLM 的决策理由(推断自 thought + action)
        :param ctx: AgentContext
        :return: Tool 返回的 dict(异常时含 error)
        """
        start_ts = datetime.utcnow()
        start_iso = start_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')

        if not self._registry.has(tool_name):
            duration_ms = 0
            error_msg = f'未注册的 Tool: {tool_name}'
            ctx.add_trace_step(
                thought=thought, decision=decision,
                action='call_tool', tool_name=tool_name,
                tool_input=args,
                observation={'error': error_msg},
                start_time=start_iso, end_time=start_iso,
                duration_ms=0, status='failed',
                error_message=error_msg,
            )
            return {'error': error_msg}

        tool = self._registry.get(tool_name)
        result = tool.safe_run(args, ctx)
        end_ts = datetime.utcnow()
        duration_ms = int((end_ts - start_ts).total_seconds() * 1000)
        end_iso = end_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')

        # 结果摘要(审计用,不存完整结果)
        is_error = isinstance(result, dict) and 'error' in result
        if is_error:
            summary = f"失败: {result['error'][:100]}"
        elif isinstance(result, dict):
            if 'risks' in result:
                summary = f"返回 {result.get('count', len(result['risks']))} 条风险"
            elif 'references' in result:
                summary = f"命中 {result.get('hit_count', 0)} 条知识"
            elif 'fields' in result:
                summary = f"返回 {result.get('field_count', 0)} 字段(缺失 {result.get('missing_count', 0)})"
            else:
                summary = '完成'
        else:
            summary = '完成'

        error = result.get('error') if isinstance(result, dict) else None
        ctx.add_tool_call(tool_name, args, duration_ms, summary, error)
        ctx.add_observation(tool_name, result)

        # v0.7.1: 记录 Trace 步骤
        ctx.add_trace_step(
            thought=thought,
            decision=decision,
            action='call_tool',
            tool_name=tool_name,
            tool_input=args,
            observation=result,
            start_time=start_iso,
            end_time=end_iso,
            duration_ms=duration_ms,
            status='failed' if is_error else 'success',
            error_message=error,
        )

        logger.info('[Agent] Tool %s 完成: %s ms, %s',
                    tool_name, duration_ms, summary)
        return result

    # ---------- 兜底报告 ----------
    def _fallback_report(self, ctx: AgentContext,
                         llm_error: Optional[str],
                         llm_error_type: Optional[str] = None,
                         iteration_exceeded: bool = False) -> AgentResult:
        """
        LLM 失败 / 达到迭代上限时,用 risk_rule_tool 兜底生成报告
        :param llm_error: LLM 失败原因(达到迭代上限时为 None)
        :param llm_error_type: LLM 错误分类(timeout/rate_limit/server_error/network/auth/framework/unknown)
        :param iteration_exceeded: 是否因迭代上限触发
        """
        logger.info('[Agent] 生成兜底报告: llm_error=%s type=%s iterations=%s exceeded=%s',
                    llm_error, llm_error_type, ctx.iterations, iteration_exceeded)

        # 直接调 risk_rule_tool(确定性)
        if not self._registry.has('risk_rule_tool'):
            ctx.add_trace_step(
                thought='兜底报告生成',
                decision='risk_rule_tool 未注册,无法生成兜底报告',
                action='system',
                observation={'error': 'risk_rule_tool 未注册'},
                start_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                end_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                duration_ms=0, status='failed',
                error_message='risk_rule_tool 未注册,无法生成兜底报告',
            )
            return AgentResult(
                status=AgentResult.FAILED,
                error='risk_rule_tool 未注册,无法生成兜底报告',
                iterations=ctx.iterations,
                tool_calls_log=ctx.tool_calls_log,
                agent_trace=ctx.agent_trace,
                trace_summary=ctx.get_trace_summary(),
            )

        tool = self._registry.get('risk_rule_tool')
        start_ts = datetime.utcnow()
        start_iso = start_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')
        result = tool.safe_run({}, ctx)
        end_ts = datetime.utcnow()
        duration_ms = int((end_ts - start_ts).total_seconds() * 1000)
        end_iso = end_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')
        ctx.add_tool_call('risk_rule_tool', {}, duration_ms,
                          f"兜底:返回 {result.get('count', 0)} 条风险",
                          result.get('error'))

        # v0.7.1: 记录兜底 Trace 步骤
        fallback_thought = 'LLM 不可用,使用规则引擎兜底' if llm_error else '达到迭代上限,使用规则引擎兜底'
        fallback_decision = '降级为 RiskRuleTool 生成确定性风险报告'
        ctx.add_trace_step(
            thought=fallback_thought,
            decision=fallback_decision,
            action='fallback',
            tool_name='risk_rule_tool',
            tool_input={},
            observation=result,
            start_time=start_iso,
            end_time=end_iso,
            duration_ms=duration_ms,
            status='failed' if result.get('error') else 'success',
            error_message=result.get('error'),
        )

        rule_risks = result.get('risks', [])
        risks = []
        for r in rule_risks:
            risk = _normalize_risk(r)
            # 规则风险无 references
            risk.setdefault('rule_id', r.get('rule_id'))
            risks.append(risk)

        risk_level = _compute_risk_level(risks)

        # v0.7.1: summary 统一注明"规则引擎降级模式"
        if llm_error:
            summary = (f'本次审核采用规则引擎降级模式({len(risks)} 条风险)。'
                       f'注:LLM 不可用({llm_error}),未做 LLM 综合分析。')
        elif iteration_exceeded:
            summary = (f'本次审核采用规则引擎降级模式({len(risks)} 条风险)。'
                       f'注:Agent Iteration Exceeded(达到迭代上限 {ctx.max_iterations}),未输出 LLM 最终报告。')
        else:
            summary = (f'本次审核采用规则引擎降级模式({len(risks)} 条风险)。'
                       f'注:达到迭代上限,未输出 LLM 最终报告。')

        return AgentResult(
            status=AgentResult.SUCCESS,
            risk_level=risk_level,
            risks=risks,
            summary=summary,
            iterations=ctx.iterations,
            llm_error=llm_error,
            llm_error_type=llm_error_type,
            tool_calls_log=ctx.tool_calls_log,
            agent_trace=ctx.agent_trace,
            trace_summary=ctx.get_trace_summary(),
        )

    # ---------- 最终报告校验 ----------
    def _build_result_from_final_report(self, decision: dict,
                                        ctx: AgentContext) -> AgentResult:
        """从 LLM final_report 决策构建 AgentResult"""
        # v0.7.1: 记录 Final Report Trace 步骤
        end_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')
        ctx.add_trace_step(
            thought=decision.get('thought', '已收集足够信息,输出最终报告'),
            decision='综合所有工具观察结果,生成最终风险报告',
            action='final_report',
            observation={
                'risk_level': decision.get('risk_level', 'none'),
                'summary': decision.get('summary', '')[:200],
                'risks_count': len(decision.get('risks', []) or []),
            },
            start_time=end_iso,
            end_time=end_iso,
            duration_ms=0,
            status='success',
        )

        risks_raw = decision.get('risks', []) or []
        risks = [_normalize_risk(r) for r in risks_raw]

        # 用计算的 risk_level 覆盖(更可靠)
        risk_level = _compute_risk_level(risks)
        # 若 LLM 给的 level 与计算一致则用 LLM 的,否则用计算的
        llm_level = decision.get('risk_level', 'none')
        if llm_level in _VALID_RISK_LEVELS and llm_level == risk_level:
            final_level = llm_level
        else:
            final_level = risk_level

        summary = decision.get('summary', '') or '审核完成'

        return AgentResult(
            status=AgentResult.SUCCESS,
            risk_level=final_level,
            risks=risks,
            summary=summary,
            iterations=ctx.iterations,
            llm_error=None,
            tool_calls_log=ctx.tool_calls_log,
            agent_trace=ctx.agent_trace,
            trace_summary=ctx.get_trace_summary(),
        )

    # ---------- 主循环 ----------
    def run(self, ctx: AgentContext) -> AgentResult:
        """
        执行 ReAct 循环

        :param ctx: AgentContext(已含 contract / fields / document_text)
        :return: AgentResult
        """
        ctx.max_iterations = self.max_iterations
        agent_start_ts = datetime.utcnow()
        logger.info('[Agent] ===== 开始审核 ===== contract_id=%s fields=%s text_len=%s max_iter=%s',
                    ctx.contract_id, len(ctx.fields), len(ctx.document_text), self.max_iterations)

        llm_error = None
        llm_error_type = None
        json_retry_used = False  # JSON 解析失败重试标志(每轮仅重试 1 次)

        while ctx.iterations < self.max_iterations:
            ctx.iterations += 1

            # ---------- 1. 构建 Prompt ----------
            human_prompt = _build_human_prompt(
                ctx, self._system_prompt, self._human_template
            )

            # ---------- 2. 调用 DeepSeek(v0.7.1: 3-tuple + 耗时统计) ----------
            llm_start = datetime.utcnow()
            llm_start_iso = llm_start.strftime('%Y-%m-%dT%H:%M:%S.%f')
            text, error, error_type = call_deepseek(self._system_prompt, human_prompt)
            llm_end = datetime.utcnow()
            llm_duration_ms = int((llm_end - llm_start).total_seconds() * 1000)
            llm_end_iso = llm_end.strftime('%Y-%m-%dT%H:%M:%S.%f')

            # 记录 LLM 调用统计
            ctx.add_llm_call(llm_duration_ms, error)

            if error:
                llm_error = error
                llm_error_type = error_type
                logger.warning('[Agent] LLM 调用失败(退出循环): type=%s error=%s duration=%sms',
                               error_type, error, llm_duration_ms)
                # v0.7.1: 记录 LLM 失败 Trace
                ctx.add_trace_step(
                    thought=f'迭代 {ctx.iterations}: 调用 LLM 决策',
                    decision='LLM 调用失败,将降级为规则引擎',
                    action='llm_call',
                    observation={'error': error, 'error_type': error_type},
                    start_time=llm_start_iso,
                    end_time=llm_end_iso,
                    duration_ms=llm_duration_ms,
                    status='failed',
                    error_message=error,
                )
                break  # 退出循环,走兜底

            # v0.7.1: 记录 LLM 成功 Trace
            ctx.add_trace_step(
                thought=f'迭代 {ctx.iterations}: 调用 LLM 决策',
                decision='LLM 返回决策 JSON,待解析',
                action='llm_call',
                observation={'response_length': len(text), 'response_preview': text[:200]},
                start_time=llm_start_iso,
                end_time=llm_end_iso,
                duration_ms=llm_duration_ms,
                status='success',
            )
            logger.info('[Agent] LLM 调用完成: %sms response_len=%s',
                        llm_duration_ms, len(text))

            # ---------- 3. 解析 JSON ----------
            decision = _extract_json(text)
            if decision is None:
                # 重试 1 次(追加"请输出合法 JSON"提示)
                if not json_retry_used:
                    json_retry_used = True
                    ctx.add_observation('system', {
                        'error': '上一次输出非合法 JSON,请重新输出严格 JSON(不要包裹代码块)'
                    })
                    # v0.7.1: 记录 JSON 重试 Trace
                    ctx.add_trace_step(
                        thought=f'迭代 {ctx.iterations}: JSON 解析失败,重试',
                        decision='追加提示让 LLM 重新输出合法 JSON',
                        action='system',
                        observation={'error': 'JSON 解析失败,重试中'},
                        start_time=llm_end_iso,
                        end_time=llm_end_iso,
                        duration_ms=0,
                        status='skipped',
                        error_message='JSON 解析失败',
                    )
                    ctx.iterations -= 1  # 不计入本轮,重试
                    continue
                else:
                    llm_error = 'LLM 输出 JSON 解析失败(重试后仍失败)'
                    llm_error_type = 'json_parse'
                    logger.warning('[Agent] %s', llm_error)
                    ctx.add_trace_step(
                        thought=f'迭代 {ctx.iterations}: JSON 二次解析失败',
                        decision='降级为规则引擎',
                        action='system',
                        observation={'error': llm_error},
                        start_time=llm_end_iso,
                        end_time=llm_end_iso,
                        duration_ms=0,
                        status='failed',
                        error_message=llm_error,
                    )
                    break  # 退出循环,走兜底

            # 重置重试标志(本轮解析成功)
            json_retry_used = False

            action = decision.get('action')
            thought = decision.get('thought', '')

            # ---------- 4. 分支处理 ----------
            if action == 'call_tool':
                tool_name = decision.get('tool', '')
                args = decision.get('args', {}) or {}
                # v0.7.1: decision 字段(决策理由)
                decision_reason = decision.get('decision', '') or thought
                logger.info('[Agent] 迭代 %s: call_tool=%s thought=%s decision=%s',
                            ctx.iterations, tool_name, thought[:50], decision_reason[:50])
                self._execute_tool(tool_name, args, thought, decision_reason, ctx)
                continue

            elif action == 'final_report':
                logger.info('[Agent] 迭代 %s: final_report', ctx.iterations)
                result = self._build_result_from_final_report(decision, ctx)
                agent_end_ts = datetime.utcnow()
                total_ms = int((agent_end_ts - agent_start_ts).total_seconds() * 1000)
                logger.info('[Agent] ===== 审核完成 ===== status=success risk=%s risks=%s '
                            'iterations=%s trace_steps=%s total=%sms llm=%sms tool=%sms',
                            result.risk_level, len(result.risks), ctx.iterations,
                            len(ctx.agent_trace), total_ms,
                            ctx.llm_stats['total_ms'],
                            sum(s.get('total_ms', 0) for s in ctx.tool_stats.values()))
                return result

            else:
                # 未知动作,追加反馈继续
                ctx.add_observation('system', {
                    'error': f'未知的 action: {action},请输出 call_tool 或 final_report'
                })
                ctx.add_trace_step(
                    thought=f'迭代 {ctx.iterations}: LLM 输出未知 action: {action}',
                    decision='追加反馈让 LLM 重新决策',
                    action='system',
                    observation={'error': f'未知 action: {action}'},
                    start_time=llm_end_iso,
                    end_time=llm_end_iso,
                    duration_ms=0,
                    status='skipped',
                    error_message=f'未知 action: {action}',
                )
                continue

        # ---------- 5. 达到迭代上限 / LLM 失败 → 兜底 ----------
        iteration_exceeded = ctx.iterations >= self.max_iterations and llm_error is None
        if iteration_exceeded:
            logger.warning('[Agent] Agent Iteration Exceeded: 达到迭代上限 %s', self.max_iterations)
            # v0.7.1: 记录迭代超限 Trace
            ctx.add_trace_step(
                thought=f'达到迭代上限 {self.max_iterations},停止 ReAct 循环',
                decision='Agent Iteration Exceeded,降级为规则引擎',
                action='iteration_exceeded',
                observation={'max_iterations': self.max_iterations, 'iterations': ctx.iterations},
                start_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                end_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                duration_ms=0,
                status='failed',
                error_message=f'Agent Iteration Exceeded (max={self.max_iterations})',
            )

        result = self._fallback_report(ctx, llm_error, llm_error_type, iteration_exceeded)
        agent_end_ts = datetime.utcnow()
        total_ms = int((agent_end_ts - agent_start_ts).total_seconds() * 1000)
        logger.info('[Agent] ===== 审核完成 ===== status=%s risk=%s risks=%s '
                    'iterations=%s trace_steps=%s total=%sms llm=%sms tool=%sms fallback=%s',
                    result.status, result.risk_level, len(result.risks), ctx.iterations,
                    len(ctx.agent_trace), total_ms, ctx.llm_stats['total_ms'],
                    sum(s.get('total_ms', 0) for s in ctx.tool_stats.values()),
                    iteration_exceeded or llm_error is not None)
        return result
