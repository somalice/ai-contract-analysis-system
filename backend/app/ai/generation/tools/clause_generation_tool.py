"""
Tool3:条款生成工具(Sprint 6 - v0.8.0)

职责:
- 调用 LLM 生成指定类型的合同条款文本(付款/违约/保密/知识产权/售后/争议解决等)
- 基于 RAG 检索内容(从 ctx.rag_references 读)+ 合同类型,生成框架性条款
- 条款文本回写 ctx.generated_clauses,并附 RAG 引用

复用 Sprint 5(只读 import,不修改):
- call_deepseek → app.ai.agent.llm_client(3-tuple 返回 + 错误分类)

约束:
- Prompt 从 prompts/clause_generation_v1.md 加载,不硬编码
- LLM 失败 → 返回 error dict,Agent 决策是否降级(不中断循环)
- 禁止编造法律条文(由 Prompt 约束)
"""
import os
from datetime import datetime

from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.generation.context import GenerationContext
from app.extensions.logger import logger


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts', 'clause_generation_v1.md'
)

# ---------- 支持的条款类型(供 LLM 参考,不强制) ----------
_SUPPORTED_CLAUSE_TYPES = (
    '付款条款', '违约责任', '保密条款', '知识产权',
    '售后服务', '争议解决', '不可抗力', '合同期限',
)


def _load_clause_prompt():
    """
    从 clause_generation_v1.md 加载 System / Human Prompt
    复用 Sprint 5 的 ## System Prompt / ## Human Prompt 解析模式
    :return: (system_prompt, human_prompt_template)
    """
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Gen:clause_tool] Prompt 文件加载失败: %s', _PROMPT_FILE)
        return (
            '你是合同条款起草专家,生成结构完整、表述严谨的条款正文。禁止编造法律条文。仅输出条款正文。',
            '【合同类型】\n{contract_type}\n\n【生成条款类型】\n{clause_type}\n\n'
            '【合同上下文】\n{context}\n\n【企业规范参考】\n{rag_context}\n\n请生成"{clause_type}"的条款正文:'
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
        system_prompt = '你是合同条款起草专家,生成条款正文。禁止编造法律条文。'
    if not human_prompt:
        human_prompt = '【合同类型】\n{contract_type}\n\n【条款类型】\n{clause_type}\n\n【上下文】\n{context}\n\n【规范】\n{rag_context}'

    return system_prompt, human_prompt


def _format_rag_context(ctx: GenerationContext) -> str:
    """格式化 RAG 引用为上下文文本(供条款生成 Prompt)"""
    refs = ctx.rag_references or []
    if not refs:
        return '(暂无企业规范参考,基于通用合同常识生成)'
    parts = []
    for i, ref in enumerate(refs[:5], 1):  # 最多取 5 条,控制 token
        title = ref.get('document_title', '未知文档')
        text = ref.get('text', '')
        if text:
            # 截断过长文本
            text = text[:300] + '...' if len(text) > 300 else text
            parts.append(f'[{i}] {title}:\n{text}')
    return '\n\n'.join(parts) if parts else '(暂无可用规范内容)'


class ClauseGenerationTool(BaseTool):
    """条款生成工具(调 LLM 生成指定类型条款文本)"""

    @property
    def name(self) -> str:
        return 'clause_generation_tool'

    @property
    def description(self) -> str:
        return (
            '调用 LLM 生成指定类型的合同条款正文(如付款条款、违约责任、保密条款、知识产权、'
            '售后服务、争议解决等)。基于企业规范与合同类型生成框架性条款,禁止编造法律条文。'
            '生成后条款回写上下文,供最终报告与 Word 渲染使用。'
            '需提供 clause_type(条款类型)参数;context(上下文)可选。'
        )

    @property
    def args_schema(self) -> dict:
        return {
            'clause_type': f'条款类型(必填,如:{"/".join(_SUPPORTED_CLAUSE_TYPES[:4])}等)',
            'context': '条款生成的额外上下文(可选,如合同金额、双方信息等)',
        }

    def run(self, args: dict, ctx: GenerationContext) -> dict:
        """
        生成指定类型条款
        :param args: {clause_type: str, context: str(可选)}
        :return: {clause_type, content, source, references, error(失败时)}
        """
        clause_type = (args or {}).get('clause_type', '')
        if not clause_type or not str(clause_type).strip():
            return {
                'clause_type': '',
                'content': '',
                'source': 'ai',
                'references': [],
                'error': 'clause_type 不能为空',
            }
        clause_type = str(clause_type).strip()
        extra_context = (args or {}).get('context', '') or ''

        # 局部 import(避免模块加载时强依赖 llm_client)
        from app.ai.agent.llm_client import call_deepseek

        # ---------- 构建 Prompt ----------
        system_prompt, human_template = _load_clause_prompt()
        rag_context = _format_rag_context(ctx)

        # 合同上下文:用户变量 + 额外 context
        context_parts = []
        if ctx.contract_type:
            context_parts.append(f'合同类型:{ctx.contract_type}')
        if ctx.input_variables:
            var_lines = [f'  {k}: {v}' for k, v in ctx.input_variables.items()
                         if v is not None and str(v).strip()]
            if var_lines:
                context_parts.append('已填变量:\n' + '\n'.join(var_lines))
        if extra_context:
            context_parts.append(f'补充说明:{extra_context}')
        context_str = '\n'.join(context_parts) if context_parts else '(无额外上下文)'

        human_prompt = human_template.format(
            contract_type=ctx.contract_type or '未分类',
            clause_type=clause_type,
            context=context_str,
            rag_context=rag_context,
        )

        # ---------- 调用 DeepSeek ----------
        start_ts = datetime.utcnow()
        # 条款生成需要较多 token,放宽 max_tokens
        text, error, error_type = call_deepseek(system_prompt, human_prompt,
                                                max_tokens=1200)
        duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

        if error:
            logger.warning('[Gen:clause_tool] LLM 生成失败: type=%s clause=%s error=%s duration=%sms',
                           error_type, clause_type, error, duration_ms)
            return {
                'clause_type': clause_type,
                'content': '',
                'source': 'ai',
                'references': [],
                'error': error,
                'llm_error_type': error_type,
            }

        # 清理 LLM 输出(去 Markdown 代码块包裹 + 首尾空白)
        content = self._clean_clause_text(text)
        if not content:
            logger.warning('[Gen:clause_tool] LLM 返回空条款: clause=%s', clause_type)
            return {
                'clause_type': clause_type,
                'content': '',
                'source': 'ai',
                'references': [],
                'error': 'LLM 返回空条款文本',
            }

        # 收集本次条款相关的 RAG 引用(全部 references 作为来源)
        references = ctx.rag_references or []

        # 回写 ctx.generated_clauses
        ctx.add_generated_clause(
            name=clause_type,
            content=content,
            source='ai',
            references=references,
        )

        logger.info('[Gen:clause_tool] 条款生成成功: clause=%s len=%s duration=%sms refs=%s',
                    clause_type, len(content), duration_ms, len(references))

        return {
            'clause_type': clause_type,
            'content': content,
            'source': 'ai',
            'references': references,
            'duration_ms': duration_ms,
        }

    def _clean_clause_text(self, text: str) -> str:
        """
        清理 LLM 输出的条款文本
        - 去除 Markdown 代码块包裹(```...```)
        - 去除首尾空白
        - 去除可能的前言(如"以下是XXX条款:")
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
