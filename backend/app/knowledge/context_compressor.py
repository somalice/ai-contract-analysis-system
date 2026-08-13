"""
Context Compressor(Sprint 8.9 Phase 2 - RAG Answer Quality Optimization)

职责:
- 在 Reranker Top5 之后、LLM 生成之前,对检索上下文做"基于 LLM 的 context extraction"
- 输入: question + retrieved_context
- 输出: 只保留回答问题必须的信息,丢弃无关条款(避免无关信息进入 Prompt)

设计约束(遵循 user_rules §11 Prompt 管理 / §19 可维护性):
- Prompt 从 prompts/context_compressor.md 加载(DB active 优先,回退文件),不硬编码
- 零新依赖: 复用 langchain_openai.ChatOpenAI 与 rag_service 同款调用模式
- 失败降级: 任何异常 → 返回原 context(不阻断 RAG 主流程,与 Reranker 降级策略一致)
- 无状态: 模块级函数,不持有 session/请求上下文

注入点:
- rag_service.query_rag(生产链路,config RAG_CONTEXT_COMPRESS=true 时启用)
- run_rag_eval._retrieve_chunks(评估链路,experiment.context_compression=true 时启用)
两路径共用 compress_context(),保持行为一致。
"""
import os
from typing import Optional

from flask import current_app
from app.extensions.logger import logger


# ---------- Prompt 文件路径 ----------
# 修复(Sprint 8.9): 原 '..' 使路径解析到 app/prompts(不存在),一直走兜底 Prompt。
# prompts 目录与 context_compressor.py 同级(均在 knowledge 下)。
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'prompts', 'context_compressor.md'
)


def _load_compressor_prompt():
    """加载压缩器 Prompt(DB active 优先,回退文件,兜底内联)。"""
    try:
        from app.services import prompt_service
        tpl = prompt_service.get_active_template('rag_answer')
    except Exception:
        tpl = None
    if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
        # 注意: 压缩器使用独立 prompt 文件;DB 模板仅当不存在时才回退
        pass
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.warning('[Knowledge:compress] 压缩器 Prompt 加载失败,使用兜底: %s', _PROMPT_FILE)
        return (
            '你是一个合同知识检索上下文压缩器。根据用户问题,从检索上下文中只提取回答问题必须的信息,'
            '逐字保留原文措辞,丢弃无关内容,不输出引导语。',
            '【用户问题】\n{question}\n\n【检索上下文】\n{context}\n\n请压缩:'
        )

    system_prompt = ''
    human_prompt = ''
    current_section = None
    system_lines = []
    human_lines = []
    for line in content.split('\n'):
        s = line.strip()
        if s == '## System Prompt':
            current_section = 'system'
            continue
        if s == '## Human Prompt':
            current_section = 'human'
            continue
        if s.startswith('## ') and current_section:
            current_section = None
            continue
        if current_section == 'system':
            system_lines.append(line)
        elif current_section == 'human':
            human_lines.append(line)
    system_prompt = '\n'.join(system_lines).strip()
    human_prompt = '\n'.join(human_lines).strip()
    if not system_prompt:
        system_prompt = '你是一个合同知识检索上下文压缩器,只提取回答问题必须的信息,忠实原文。'
    if not human_prompt:
        human_prompt = '【用户问题】\n{question}\n\n【检索上下文】\n{context}\n\n请压缩:'
    return system_prompt, human_prompt


def compress_context(question: str, context_str: str,
                     max_input_chars: Optional[int] = None) -> str:
    """
    对检索 context 做 LLM 压缩:只保留回答问题必须的信息。

    :param question: 用户问题
    :param context_str: 检索上下文(带 [文档n] 标注的拼接文本)
    :param max_input_chars: context 超长时才触发压缩(短 context 直接返回,省一次 LLM 调用);
        None → 读 config RAG_CONTEXT_COMPRESS_MIN_CHARS(默认 6000)
    :return: 压缩后的 context;任何异常 / 压缩结果异常 → 返回原 context(降级不阻断)
    """
    if not context_str or not context_str.strip():
        return context_str
    if max_input_chars is None:
        try:
            max_input_chars = int(current_app.config.get(
                'RAG_CONTEXT_COMPRESS_MIN_CHARS', 6000) or 6000)
        except Exception:
            max_input_chars = 6000
    # 短 context 无需压缩(避免为每道题都多一次 LLM 调用)
    if len(context_str) <= max_input_chars:
        return context_str

    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return context_str

    try:
        import httpx
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        logger.warning('[Knowledge:compress] langchain 未安装,跳过压缩')
        return context_str

    try:
        _timeout = httpx.Timeout(
            timeout=current_app.config.get('LLM_READ_TIMEOUT', 20),
            connect=current_app.config.get('LLM_CONNECT_TIMEOUT', 5),
        )
        llm = ChatOpenAI(
            model_name=current_app.config['DEEPSEEK_MODEL'],
            openai_api_key=api_key,
            openai_api_base=current_app.config['DEEPSEEK_API_BASE'],
            temperature=0.0,
            max_tokens=current_app.config.get('LLM_RAG_MAX_TOKENS', 768),
            timeout=_timeout,
            max_retries=0,  # 压缩失败不重试,快速降级
        )
        system_prompt, human_prompt = _load_compressor_prompt()
        prompt = ChatPromptTemplate.from_messages([
            ('system', system_prompt),
            ('human', human_prompt),
        ])
        chain = prompt | llm
        response = chain.invoke({'question': question, 'context': context_str})
        compressed = response.content if hasattr(response, 'content') else str(response)
        compressed = (compressed or '').strip()
        # 异常输出(空 / 无相关内容占位)→ 视为压缩失败,回退原 context
        if not compressed or compressed == '无相关内容':
            return context_str
        logger.info('[Knowledge:compress] context 压缩: %d → %d 字符',
                    len(context_str), len(compressed))
        return compressed
    except Exception as e:
        logger.warning('[Knowledge:compress] 压缩失败,回退原 context: %s', e)
        return context_str
