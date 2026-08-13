"""
Proposal Agent(Sprint 7 - v0.9.0)

职责:
- ReAct 循环主体:LLM 决策 → Tool 执行 → 观察结果 → 再决策 → 最终生成结果
- 手写实现(不引入 LangGraph / Agent 框架),镜像 Sprint 6 GenerationAgent

执行流程:
1. 加载 Prompt(bid_proposal_v1.md)
2. 注册 5 个 Tool(RequirementTool / BidKnowledgeSearchTool / CompanyProfileTool /
   ProposalSectionTool / ComplianceRuleTool)
3. ReAct 循环(最多 max_iterations 轮):
   a. 构建 Human Prompt(招标信息 + 需求 + 企业资料 + 已生成章节 + RAG + 观察)
   b. 调用 DeepSeek
   c. 解析 JSON 决策
   d. call_tool → 执行 → 观察入 ctx → 继续
   e. final_report → 校验 → 返回
4. LLM 失败 / 达到迭代上限 → 兜底(仅 compliance_rule_tool 校验,无 AI 章节)

容错:
- LLM 不可用 / JSON 解析失败 → 兜底(规则校验,无 AI 章节),仍返回 success(可渲染骨架)
- Tool 异常 → safe_run 返回 error dict,不中断循环
- 迭代上限 → 兜底

约束:
- 不直接访问数据库(通过 Tool)
- 不硬编码 Prompt(从 prompts/ 加载)
- 禁止 print() / return str(e)
- 不修改 Sprint 5/6 任何 Agent 类
"""
import os
from datetime import datetime
from typing import Optional

from app.extensions.logger import logger

from app.ai.agent.llm_client import call_deepseek  # 复用 Sprint 5
from app.ai.agent.tool_registry import ToolRegistry  # 复用 Sprint 5
from app.ai.bid.context import ProposalContext
from app.ai.bid.result import ProposalResult
from app.ai.bid.json_utils import extract_json
from app.ai.bid.tools import (
    RequirementTool,
    BidKnowledgeSearchTool,
    CompanyProfileTool,
    ProposalSectionTool,
    ComplianceRuleTool,
)


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'prompts', 'bid_proposal_v1.md'
)


# ============================================================
# Prompt 加载与构建
# ============================================================
def _load_prompt():
    """
    Sprint 8 新增:DB active 模板优先,失败回退原文件解析逻辑。
    :return: (system_prompt, human_prompt_template)
    """
    # Sprint 8: DB active Prompt 优先
    try:
        from app.services import prompt_service
        tpl = prompt_service.get_active_template('bid_proposal')
        if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
            return tpl['system_prompt'], tpl['human_prompt']
    except Exception as _e:
        logger.warning('[Bid:agent] PromptTemplate DB 查询失败,回退原 .md 文件: %s', _e)

    # ---------- Sprint 0~7 原逻辑(100% 保留,作为 fallback)----------
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Bid:agent] Prompt 文件加载失败: %s', _PROMPT_FILE)
        return (
            '你是投标方案生成 Agent。通过调用工具收集信息,输出严格 JSON 决策。'
            '动作:call_tool(调用工具)或 final_report(最终报告)。禁止编造企业资质/业绩。',
            '【招标信息】\n{bid_info}\n\n【招标需求】\n{requirements}\n\n【企业资料】\n{company_profile}\n\n'
            '【已生成章节】\n{generated_sections}\n\n【RAG 检索结果】\n{rag_context}\n\n'
            '【工具观察历史】\n{observations}\n\n迭代:{iterations}/{max_iterations}'
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
        system_prompt = '你是投标方案生成 Agent,输出严格 JSON 决策。'
    if not human_prompt:
        human_prompt = (
            '{bid_info}\n{requirements}\n{company_profile}\n{generated_sections}\n'
            '{rag_context}\n{observations}\n{iterations}/{max_iterations}'
        )

    return system_prompt, human_prompt


def _format_bid_info(ctx: ProposalContext) -> str:
    """格式化招标文件信息(供 Prompt)"""
    bid = ctx.bid_info or {}
    lines = [
        f"招标编号:{bid.get('bid_no', '未知')}",
        f"标题:{bid.get('title', '未知')}",
        f"上传者:{bid.get('uploader', {}).get('username', '未知') if isinstance(bid.get('uploader'), dict) else '未知'}",
    ]
    return '\n'.join(lines)


def _format_requirements(ctx: ProposalContext) -> str:
    """格式化招标需求(供 Prompt)"""
    req = ctx.requirements or {}
    if not req:
        return '(招标需求未提取,建议先调用 requirement_tool 查看)'
    lines = [
        f"项目名称:{req.get('project_name', '(未提取)')}",
        f"招标单位:{req.get('tender_org', '(未提取)')}",
        f"预算:{req.get('budget', '(未提取)')}",
        f"截止时间:{req.get('deadline', '(未提取)')}",
        f"工期/服务期:{req.get('duration', '(未提取)')}",
        f"供货范围:{req.get('delivery_requirements', '(未提取)')}",
        f"付款条件:{req.get('payment_terms', '(未提取)')}",
    ]
    tech_reqs = req.get('technical_requirements') or []
    if tech_reqs:
        lines.append(f'技术要求({len(tech_reqs)} 项):')
        for i, t in enumerate(tech_reqs[:5], 1):
            text = str(t)[:150] + '...' if len(str(t)) > 150 else str(t)
            lines.append(f'  {i}. {text}')
    qual_reqs = req.get('qualification_requirements') or []
    if qual_reqs:
        lines.append(f'资格要求({len(qual_reqs)} 项):')
        for i, q in enumerate(qual_reqs[:5], 1):
            text = str(q)[:150] + '...' if len(str(q)) > 150 else str(q)
            lines.append(f'  {i}. {text}')
    scoring = req.get('scoring_criteria') or []
    if scoring:
        lines.append(f'评分标准({len(scoring)} 项):')
        for i, s in enumerate(scoring[:3], 1):
            text = str(s)[:150] + '...' if len(str(s)) > 150 else str(s)
            lines.append(f'  {i}. {text}')
    return '\n'.join(lines)


def _format_company_profile(ctx: ProposalContext) -> str:
    """格式化企业资料(供 Prompt)"""
    profile = ctx.company_profile or {}
    if not profile or not profile.get('available'):
        return '(企业资料未上传,生成通用章节,资质用"详见附件"占位)'
    lines = [
        f"公司名称:{profile.get('company_name', '(未提供)')}",
        f"公司简介:{profile.get('brief', '(未提供)')}",
    ]
    quals = profile.get('qualifications') or []
    if quals:
        lines.append(f'资质清单({len(quals)} 项,展示前 5 项):')
        for i, q in enumerate(quals[:5], 1):
            lines.append(f'  {i}. {q}')
    projects = profile.get('past_projects') or []
    if projects:
        lines.append(f'业绩案例({len(projects)} 项,展示前 5 项):')
        for i, p in enumerate(projects[:5], 1):
            lines.append(f'  {i}. {p}')
    return '\n'.join(lines)


def _format_generated_sections(ctx: ProposalContext) -> str:
    """格式化已生成章节(供 Prompt)"""
    sections = ctx.generated_sections or []
    if not sections:
        return '(尚未生成章节,建议调用 proposal_section_tool 生成必填章节)'
    lines = []
    for s in sections:
        section_type = s.get('section_type', '?')
        section_name = s.get('section_name', '?')
        content = s.get('content', '')
        # 截断过长内容,控制 token
        content_preview = content[:200] + '...' if len(content) > 200 else content
        lines.append(f"- {section_type}({section_name}):\n{content_preview}")
    return '\n'.join(lines)


def _format_rag_context(ctx: ProposalContext) -> str:
    """格式化 RAG 检索结果(供 Prompt)"""
    refs = ctx.rag_references or []
    if not refs:
        return '(尚未检索企业规范,可调用 bid_knowledge_search_tool)'
    parts = []
    for i, ref in enumerate(refs[:5], 1):  # 最多 5 条
        title = ref.get('document_title', '未知文档')
        text = ref.get('text', '')
        text = text[:200] + '...' if len(text) > 200 else text
        parts.append(f'[{i}] {title}:\n{text}')
    return '\n\n'.join(parts)


def _format_observations(ctx: ProposalContext) -> str:
    """格式化工具观察历史(供 Prompt)"""
    if not ctx.observations:
        return '(尚未调用任何工具,建议先调用 requirement_tool 了解需求)'
    parts = []
    for i, obs in enumerate(ctx.observations, 1):
        tool = obs.get('tool', '?')
        result = obs.get('result', {})
        import json
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > 1500:
            result_str = result_str[:1500] + '...(截断)'
        parts.append(f'[{i}] 工具 {tool} 返回:\n{result_str}')
    return '\n\n'.join(parts)


def _build_human_prompt(ctx: ProposalContext, human_template: str) -> str:
    """构建 Human Prompt(填充占位符)"""
    return human_template.format(
        bid_info=_format_bid_info(ctx),
        requirements=_format_requirements(ctx),
        company_profile=_format_company_profile(ctx),
        generated_sections=_format_generated_sections(ctx),
        rag_context=_format_rag_context(ctx),
        observations=_format_observations(ctx),
        iterations=ctx.iterations,
        max_iterations=ctx.max_iterations,
    )


# ============================================================
# ProposalAgent
# ============================================================
class ProposalAgent:
    """投标生成 Agent(ReAct 循环)"""

    def __init__(self, max_iterations: int = None):
        """
        :param max_iterations: ReAct 最大迭代次数(None 时从 config 读取,默认 5)
        """
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
        return 'proposal_agent'

    def _register_default_tools(self):
        """注册 5 个默认 Tool"""
        self._registry.register(RequirementTool())
        self._registry.register(BidKnowledgeSearchTool())
        self._registry.register(CompanyProfileTool())
        self._registry.register(ProposalSectionTool())
        self._registry.register(ComplianceRuleTool())

    # ---------- Tool 执行 ----------
    def _execute_tool(self, tool_name: str, args: dict,
                      thought: str, decision: str,
                      ctx: ProposalContext) -> dict:
        """
        执行 Tool 并记录日志 + 观察 + Trace
        :return: Tool 返回的 dict(异常时含 error)
        """
        start_ts = datetime.utcnow()
        start_iso = start_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')

        if not self._registry.has(tool_name):
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

        # 结果摘要(审计用)
        is_error = isinstance(result, dict) and 'error' in result
        if is_error:
            summary = f"失败: {result['error'][:100]}"
        elif isinstance(result, dict):
            if 'field_count' in result:
                summary = f"返回需求 {result.get('field_count', 0)}/15 字段(缺失 {result.get('missing_count', 0)})"
            elif 'references' in result:
                summary = f"命中 {result.get('hit_count', 0)} 条规范"
            elif 'available' in result:
                summary = f"企业资料{'可用' if result.get('available') else '不可用'}"
            elif 'section_name' in result:
                summary = f"生成章节 {result.get('section_name', '?')}(len={len(result.get('content', ''))})"
            elif 'passed' in result:
                summary = f"校验{'通过' if result.get('passed') else '未通过'}({len(result.get('issues', []))} 项问题)"
            else:
                summary = '完成'
        else:
            summary = '完成'

        error = result.get('error') if isinstance(result, dict) else None
        ctx.add_tool_call(tool_name, args, duration_ms, summary, error)
        ctx.add_observation(tool_name, result)

        # 记录 Trace 步骤
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

        logger.info('[Bid:agent] Tool %s 完成: %s ms, %s',
                    tool_name, duration_ms, summary)

        # ---------- RAG 引用聚合(镜像 Sprint 6 Hotfix-1) ----------
        # Tool 返回 references 时自动累积到 ctx.rag_references
        if isinstance(result, dict) and result.get('references'):
            ctx.add_rag_references(result['references'])

        return result

    # ---------- 兜底(规则校验,无 AI 章节) ----------
    def _fallback(self, ctx: ProposalContext,
                  llm_error: Optional[str],
                  llm_error_type: Optional[str] = None,
                  iteration_exceeded: bool = False) -> ProposalResult:
        """
        LLM 失败 / 达到迭代上限时,仅执行 compliance_rule_tool 兜底
        - 不生成 AI 章节(generated_sections 保持空)
        - 执行规则校验,返回校验结果
        - 仍返回 success(可渲染,只是无 AI 章节内容)
        """
        logger.info('[Bid:agent] 生成兜底: llm_error=%s type=%s iterations=%s exceeded=%s',
                    llm_error, llm_error_type, ctx.iterations, iteration_exceeded)

        fallback_thought = 'LLM 不可用,使用规则校验兜底' if llm_error else '达到迭代上限,使用规则校验兜底'
        fallback_decision = '降级为 ComplianceRuleTool 仅做规则校验,不生成 AI 章节'

        if self._registry.has('compliance_rule_tool'):
            tool = self._registry.get('compliance_rule_tool')
            start_ts = datetime.utcnow()
            start_iso = start_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')
            result = tool.safe_run({}, ctx)
            end_ts = datetime.utcnow()
            duration_ms = int((end_ts - start_ts).total_seconds() * 1000)
            end_iso = end_ts.strftime('%Y-%m-%dT%H:%M:%S.%f')
            ctx.add_tool_call('compliance_rule_tool', {}, duration_ms,
                              f"兜底:校验{'通过' if result.get('passed') else '未通过'}",
                              result.get('error'))
            ctx.add_trace_step(
                thought=fallback_thought,
                decision=fallback_decision,
                action='fallback',
                tool_name='compliance_rule_tool',
                tool_input={},
                observation=result,
                start_time=start_iso,
                end_time=end_iso,
                duration_ms=duration_ms,
                status='failed' if result.get('error') else 'success',
                error_message=result.get('error'),
            )

        if llm_error:
            summary = (f'本次生成采用规则校验降级模式(无 AI 章节)。'
                       f'注:LLM 不可用({llm_error}),未做 AI 章节生成。')
        elif iteration_exceeded:
            summary = (f'本次生成采用规则校验降级模式(无 AI 章节)。'
                       f'注:Agent Iteration Exceeded(达到迭代上限 {ctx.max_iterations})。')
        else:
            summary = '本次生成采用规则校验降级模式(无 AI 章节)。'

        return ProposalResult(
            status=ProposalResult.SUCCESS,
            generated_sections=ctx.generated_sections,
            rag_references=ctx.rag_references,
            validation_results=ctx.validation_results,
            summary=summary,
            iterations=ctx.iterations,
            llm_error=llm_error,
            llm_error_type=llm_error_type,
            tool_calls_log=ctx.tool_calls_log,
            agent_trace=ctx.agent_trace,
            trace_summary=ctx.get_trace_summary(),
        )

    # ---------- 最终报告构建 ----------
    def _build_result_from_final_report(self, decision: dict,
                                        ctx: ProposalContext) -> ProposalResult:
        """从 LLM final_report 决策构建 ProposalResult"""
        end_iso = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')
        ctx.add_trace_step(
            thought=decision.get('thought', '已收集足够信息,输出最终生成结果'),
            decision='综合所有工具观察,输出最终生成结果',
            action='final_report',
            observation={
                'sections_count': len(ctx.generated_sections),
                'validation_passed': ctx.validation_results.get('passed', False),
                'summary': decision.get('summary', '')[:200],
            },
            start_time=end_iso,
            end_time=end_iso,
            duration_ms=0,
            status='success',
        )

        summary = decision.get('summary', '') or '投标方案生成完成'

        return ProposalResult(
            status=ProposalResult.SUCCESS,
            generated_sections=ctx.generated_sections,
            rag_references=ctx.rag_references,
            validation_results=ctx.validation_results,
            summary=summary,
            iterations=ctx.iterations,
            llm_error=None,
            tool_calls_log=ctx.tool_calls_log,
            agent_trace=ctx.agent_trace,
            trace_summary=ctx.get_trace_summary(),
        )

    # ---------- 主循环 ----------
    def run(self, ctx: ProposalContext) -> ProposalResult:
        """
        执行 ReAct 循环

        :param ctx: ProposalContext(已含 bid_info / requirements / company_profile)
        :return: ProposalResult
        """
        ctx.max_iterations = self.max_iterations
        agent_start_ts = datetime.utcnow()
        logger.info('[Bid:agent] ===== 开始生成 ===== bid_id=%s req_fields=%s company=%s max_iter=%s',
                    ctx.bid_info.get('id'), len(ctx.requirements),
                    ctx.company_profile.get('available'), self.max_iterations)

        llm_error = None
        llm_error_type = None
        json_retry_used = False

        while ctx.iterations < self.max_iterations:
            ctx.iterations += 1

            # ---------- 1. 构建 Prompt ----------
            human_prompt = _build_human_prompt(ctx, self._human_template)

            # ---------- 2. 调用 DeepSeek ----------
            llm_start = datetime.utcnow()
            llm_start_iso = llm_start.strftime('%Y-%m-%dT%H:%M:%S.%f')
            text, error, error_type = call_deepseek(self._system_prompt, human_prompt)
            llm_end = datetime.utcnow()
            llm_duration_ms = int((llm_end - llm_start).total_seconds() * 1000)
            llm_end_iso = llm_end.strftime('%Y-%m-%dT%H:%M:%S.%f')

            ctx.add_llm_call(llm_duration_ms, error)

            if error:
                llm_error = error
                llm_error_type = error_type
                logger.warning('[Bid:agent] LLM 调用失败(退出循环): type=%s error=%s duration=%sms',
                               error_type, error, llm_duration_ms)
                ctx.add_trace_step(
                    thought=f'迭代 {ctx.iterations}: 调用 LLM 决策',
                    decision='LLM 调用失败,将降级为规则校验',
                    action='llm_call',
                    observation={'error': error, 'error_type': error_type},
                    start_time=llm_start_iso,
                    end_time=llm_end_iso,
                    duration_ms=llm_duration_ms,
                    status='failed',
                    error_message=error,
                )
                break  # 退出循环,走兜底

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
            logger.info('[Bid:agent] LLM 调用完成: %sms response_len=%s',
                        llm_duration_ms, len(text))

            # ---------- 3. 解析 JSON ----------
            decision = extract_json(text)
            if decision is None:
                if not json_retry_used:
                    json_retry_used = True
                    ctx.add_observation('system', {
                        'error': '上一次输出非合法 JSON,请重新输出严格 JSON(不要包裹代码块)'
                    })
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
                    logger.warning('[Bid:agent] %s', llm_error)
                    ctx.add_trace_step(
                        thought=f'迭代 {ctx.iterations}: JSON 二次解析失败',
                        decision='降级为规则校验',
                        action='system',
                        observation={'error': llm_error},
                        start_time=llm_end_iso,
                        end_time=llm_end_iso,
                        duration_ms=0,
                        status='failed',
                        error_message=llm_error,
                    )
                    break  # 退出循环,走兜底

            json_retry_used = False

            action = decision.get('action')
            thought = decision.get('thought', '')

            # ---------- 4. 分支处理 ----------
            if action == 'call_tool':
                tool_name = decision.get('tool', '')
                args = decision.get('args', {}) or {}
                decision_reason = decision.get('decision', '') or thought
                logger.info('[Bid:agent] 迭代 %s: call_tool=%s thought=%s',
                            ctx.iterations, tool_name, thought[:50])
                self._execute_tool(tool_name, args, thought, decision_reason, ctx)
                continue

            elif action == 'final_report':
                logger.info('[Bid:agent] 迭代 %s: final_report', ctx.iterations)
                result = self._build_result_from_final_report(decision, ctx)
                agent_end_ts = datetime.utcnow()
                total_ms = int((agent_end_ts - agent_start_ts).total_seconds() * 1000)
                logger.info('[Bid:agent] ===== 生成完成 ===== status=success sections=%s '
                            'refs=%s iterations=%s trace_steps=%s total=%sms',
                            len(result.generated_sections), len(result.rag_references),
                            ctx.iterations, len(ctx.agent_trace), total_ms)
                return result

            else:
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
            logger.warning('[Bid:agent] Agent Iteration Exceeded: 达到迭代上限 %s',
                           self.max_iterations)
            ctx.add_trace_step(
                thought=f'达到迭代上限 {self.max_iterations},停止 ReAct 循环',
                decision='Agent Iteration Exceeded,降级为规则校验',
                action='iteration_exceeded',
                observation={'max_iterations': self.max_iterations, 'iterations': ctx.iterations},
                start_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                end_time=datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),
                duration_ms=0,
                status='failed',
                error_message=f'Agent Iteration Exceeded (max={self.max_iterations})',
            )

        result = self._fallback(ctx, llm_error, llm_error_type, iteration_exceeded)
        agent_end_ts = datetime.utcnow()
        total_ms = int((agent_end_ts - agent_start_ts).total_seconds() * 1000)
        logger.info('[Bid:agent] ===== 生成完成 ===== status=%s sections=%s refs=%s '
                    'iterations=%s trace_steps=%s total=%sms fallback=%s',
                    result.status, len(result.generated_sections), len(result.rag_references),
                    ctx.iterations, len(ctx.agent_trace), total_ms,
                    iteration_exceeded or llm_error is not None)
        return result
