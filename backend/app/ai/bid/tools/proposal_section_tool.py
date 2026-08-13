"""
Tool4:投标章节生成工具(Sprint 7 - v0.9.0)

职责:
- 调用 LLM 生成指定类型的投标章节正文(technical/commercial/responsive/qualification/summary)
- 基于 RAG 检索内容(从 ctx.rag_references 读)+ 招标需求 + 企业资料,生成章节
- 章节文本回写 ctx.generated_sections,并附 RAG 引用

复用 Sprint 5(只读 import,不修改):
- call_deepseek → app.ai.agent.llm_client(3-tuple 返回 + 错误分类)

约束:
- Prompt 从 prompts/proposal_section_v1.md 加载,不硬编码
- LLM 失败 → 返回 error dict,Agent 决策是否降级(不中断循环)
- 禁止编造企业资质/业绩(由 Prompt 约束)
镜像:Sprint 6 clause_generation_tool
"""
import os
from datetime import datetime

from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.bid.context import ProposalContext
from app.extensions.logger import logger


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts', 'proposal_section_v1.md'
)

# ---------- 支持的章节类型 + 中文名 ----------
_SECTION_TYPES = {
    'technical': '技术方案',
    'commercial': '商务文件',
    'responsive': '响应文件',
    'qualification': '资质文件',
    'summary': '投标摘要',
}


def _load_section_prompt():
    """
    从 proposal_section_v1.md 加载 System / Human Prompt
    复用 Sprint 5/6 的 ## System Prompt / ## Human Prompt 解析模式
    :return: (system_prompt, human_prompt_template)
    """
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Bid:section_tool] Prompt 文件加载失败: %s', _PROMPT_FILE)
        return (
            '你是投标文件撰写专家,生成结构完整、表述严谨的章节正文。禁止编造企业资质/业绩。'
            '仅输出章节正文(Markdown 文本)。',
            '【招标需求】\n{requirements}\n\n【企业资料】\n{company_profile}\n\n'
            '【企业规范参考】\n{rag_context}\n\n【生成章节类型】\n{section_type}({section_name})\n\n'
            '【已有章节摘要】\n{existing_sections}\n\n请生成"{section_name}"章节正文:'
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
        system_prompt = '你是投标文件撰写专家,生成章节正文。禁止编造企业资质/业绩。'
    if not human_prompt:
        human_prompt = (
            '【招标需求】\n{requirements}\n\n【企业资料】\n{company_profile}\n\n'
            '【规范参考】\n{rag_context}\n\n【章节类型】\n{section_type}({section_name})\n\n'
            '【已有章节】\n{existing_sections}'
        )

    return system_prompt, human_prompt


def _format_requirements(ctx: ProposalContext) -> str:
    """格式化招标需求(供 Prompt)"""
    req = ctx.requirements or {}
    if not req:
        return '(招标需求未提取,生成通用章节)'
    lines = [
        f"项目名称:{req.get('project_name', '(未提取)')}",
        f"招标单位:{req.get('tender_org', '(未提取)')}",
        f"预算:{req.get('budget', '(未提取)')}",
        f"截止时间:{req.get('deadline', '(未提取)')}",
        f"工期/服务期:{req.get('duration', '(未提取)')}",
        f"供货范围/交货要求:{req.get('delivery_requirements', '(未提取)')}",
        f"付款条件:{req.get('payment_terms', '(未提取)')}",
    ]
    # 技术要求清单
    tech_reqs = req.get('technical_requirements') or []
    if tech_reqs:
        lines.append('技术要求清单:')
        for i, t in enumerate(tech_reqs, 1):
            text = str(t)[:200] + '...' if len(str(t)) > 200 else str(t)
            lines.append(f'  {i}. {text}')
    # 资格要求清单
    qual_reqs = req.get('qualification_requirements') or []
    if qual_reqs:
        lines.append('资格要求清单:')
        for i, q in enumerate(qual_reqs, 1):
            text = str(q)[:200] + '...' if len(str(q)) > 200 else str(q)
            lines.append(f'  {i}. {text}')
    # 评分标准
    scoring = req.get('scoring_criteria') or []
    if scoring:
        lines.append('评分标准:')
        for i, s in enumerate(scoring, 1):
            text = str(s)[:200] + '...' if len(str(s)) > 200 else str(s)
            lines.append(f'  {i}. {text}')
    return '\n'.join(lines)


def _format_company_profile(ctx: ProposalContext) -> str:
    """格式化企业资料(供 Prompt)"""
    profile = ctx.company_profile or {}
    if not profile or not profile.get('available'):
        return '(企业资料未上传,生成通用章节,资质部分用"详见附件"占位)'
    lines = [
        f"公司名称:{profile.get('company_name', '(未提供)')}",
        f"公司简介:{profile.get('brief', '(未提供)')}",
    ]
    quals = profile.get('qualifications') or []
    if quals:
        lines.append('资质清单:')
        for i, q in enumerate(quals[:10], 1):
            lines.append(f'  {i}. {q}')
    projects = profile.get('past_projects') or []
    if projects:
        lines.append('业绩案例:')
        for i, p in enumerate(projects[:10], 1):
            lines.append(f'  {i}. {p}')
    return '\n'.join(lines)


def _format_rag_context(ctx: ProposalContext) -> str:
    """格式化 RAG 引用为上下文文本(供章节生成 Prompt)"""
    refs = ctx.rag_references or []
    if not refs:
        return '(暂无企业规范参考,基于通用投标常识生成)'
    parts = []
    for i, ref in enumerate(refs[:5], 1):  # 最多取 5 条,控制 token
        title = ref.get('document_title', '未知文档')
        text = ref.get('text', '')
        if text:
            text = text[:300] + '...' if len(text) > 300 else text
            parts.append(f'[{i}] {title}:\n{text}')
    return '\n\n'.join(parts) if parts else '(暂无可用规范内容)'


def _format_existing_sections(ctx: ProposalContext) -> str:
    """格式化已生成章节摘要(避免重复)"""
    sections = ctx.generated_sections or []
    if not sections:
        return '(尚未生成章节)'
    parts = []
    for s in sections:
        section_type = s.get('section_type', '?')
        section_name = s.get('section_name', '?')
        content = s.get('content', '')
        # 仅取前 100 字作摘要
        preview = content[:100] + '...' if len(content) > 100 else content
        parts.append(f'- {section_type}({section_name}): {preview}')
    return '\n'.join(parts)


class ProposalSectionTool(BaseTool):
    """投标章节生成工具(调 LLM 生成指定类型章节正文)"""

    @property
    def name(self) -> str:
        return 'proposal_section_tool'

    @property
    def description(self) -> str:
        return (
            '调用 LLM 生成指定类型的投标章节正文(technical=技术方案、commercial=商务文件、'
            'responsive=响应文件、qualification=资质文件、summary=投标摘要)。'
            '基于招标需求、企业资料与企业规范参考生成,禁止编造企业资质/业绩。'
            '生成后章节回写上下文,供最终报告与 Word 渲染使用。'
            '需提供 section_type 参数(必填);context(额外上下文)可选。'
        )

    @property
    def args_schema(self) -> dict:
        return {
            'section_type': f'章节类型(必填,允许: {"/".join(_SECTION_TYPES.keys())})',
            'context': '章节生成的额外上下文(可选,如特定技术指标响应)',
        }

    def run(self, args: dict, ctx: ProposalContext) -> dict:
        """
        生成指定类型章节
        :param args: {section_type: str, context: str(可选)}
        :return: {section_type, section_name, content, source, references, error(失败时)}
        """
        section_type = (args or {}).get('section_type', '')
        if not section_type or not str(section_type).strip():
            return {
                'section_type': '',
                'section_name': '',
                'content': '',
                'source': 'ai',
                'references': [],
                'error': 'section_type 不能为空',
            }
        section_type = str(section_type).strip().lower()

        if section_type not in _SECTION_TYPES:
            return {
                'section_type': section_type,
                'section_name': '',
                'content': '',
                'source': 'ai',
                'references': [],
                'error': f'section_type 非法,允许: {", ".join(_SECTION_TYPES.keys())}',
            }

        section_name = _SECTION_TYPES[section_type]
        extra_context = (args or {}).get('context', '') or ''

        # 局部 import(避免模块加载时强依赖 llm_client)
        from app.ai.agent.llm_client import call_deepseek

        # ---------- 构建 Prompt ----------
        system_prompt, human_template = _load_section_prompt()
        requirements_str = _format_requirements(ctx)
        company_profile_str = _format_company_profile(ctx)
        rag_context_str = _format_rag_context(ctx)
        existing_sections_str = _format_existing_sections(ctx)

        # 额外上下文追加到 requirements
        if extra_context:
            requirements_str = requirements_str + f'\n\n【额外上下文】\n{extra_context}'

        human_prompt = human_template.format(
            requirements=requirements_str,
            company_profile=company_profile_str,
            rag_context=rag_context_str,
            section_type=section_type,
            section_name=section_name,
            existing_sections=existing_sections_str,
        )

        # ---------- 调用 DeepSeek ----------
        start_ts = datetime.utcnow()
        # 章节正文需要较多 token
        text, error, error_type = call_deepseek(system_prompt, human_prompt,
                                                max_tokens=2000)
        duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

        if error:
            logger.warning('[Bid:section_tool] LLM 生成失败: type=%s section=%s error=%s duration=%sms',
                           error_type, section_type, error, duration_ms)
            return {
                'section_type': section_type,
                'section_name': section_name,
                'content': '',
                'source': 'ai',
                'references': [],
                'error': error,
                'llm_error_type': error_type,
            }

        # 清理 LLM 输出(去 Markdown 代码块包裹 + 首尾空白)
        content = self._clean_section_text(text)
        if not content:
            logger.warning('[Bid:section_tool] LLM 返回空章节: section=%s', section_type)
            return {
                'section_type': section_type,
                'section_name': section_name,
                'content': '',
                'source': 'ai',
                'references': [],
                'error': 'LLM 返回空章节文本',
            }

        # 收集本次章节相关的 RAG 引用(全部 references 作为来源)
        references = ctx.rag_references or []

        # 回写 ctx.generated_sections
        ctx.add_generated_section(
            section_type=section_type,
            section_name=section_name,
            content=content,
            source='ai',
            references=references,
        )

        logger.info('[Bid:section_tool] 章节生成成功: section=%s len=%s duration=%sms refs=%s',
                    section_type, len(content), duration_ms, len(references))

        return {
            'section_type': section_type,
            'section_name': section_name,
            'content': content,
            'source': 'ai',
            'references': references,
            'duration_ms': duration_ms,
        }

    def _clean_section_text(self, text: str) -> str:
        """
        清理 LLM 输出的章节文本
        - 去除 Markdown 代码块包裹(```...```)
        - 去除首尾空白
        - 去除可能的前言(如"以下是XXX章节:")
        """
        if not text:
            return ''
        text = text.strip()
        # 去除代码块包裹
        if text.startswith('```'):
            lines = text.split('\n')
            if lines and lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines).strip()
        return text
