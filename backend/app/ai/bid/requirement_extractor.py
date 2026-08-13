"""
招标需求提取器(Sprint 7.1 - v0.9.1 增强)

职责(与 v0.9.0 保持兼容):
- 从招标文件全文中提取 15 个核心字段,返回结构化 Requirement JSON
- 长文本用 SemanticChunker 切分,取前 ~6000 字(避免超 LLM 上下文)
- 复用 call_deepseek(只读 import,不修改 Sprint 5)
- 复用 SemanticChunker(只读 import,不修改 Sprint 4)

v0.9.1 新增输出:
- field_sources: {field_name: {page_number, chunk_id, confidence, source_text}}
  每个字段的来源信息,供前端溯源展示
- chunks_metadata: 发送给 LLM 的每个 Chunk 的信息,供来源匹配用

复用清单(只读 import):
- call_deepseek → app.ai.agent.llm_client(3-tuple 返回 + 错误分类)
- SemanticChunker → app.knowledge.chunk(Sprint 4)

输出结构:
{
  requirement_data: {15 字段 + confidence},
  field_count/missing_count/confidence/error(同上 v0.9.0),
  field_sources: dict|null,     # v0.9.1 新增,15 字段来源追踪
  chunks_metadata: list|null,   # v0.9.1 新增,Chunk 元数据(排障用)
}

约束:
- Prompt 从 prompts/bid_requirement_v1.md 加载,不硬编码
- LLM 失败 / JSON 解析失败 → 返回 error(不抛异常,由调用方决策)
- 禁止 print() / return str(e)
"""
from __future__ import annotations

import os
from typing import Optional

from app.extensions.logger import logger

from .json_utils import extract_json


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'prompts', 'bid_requirement_v1.md'
)

# ---------- 15 字段清单(供 missing_count 计算) ----------
_REQUIREMENT_FIELDS = (
    'project_name', 'tender_org', 'project_location', 'budget', 'deadline',
    'duration', 'delivery_requirements', 'technical_requirements',
    'qualification_requirements', 'scoring_criteria', 'bid_opening_time',
    'bid_validity', 'payment_terms', 'contact', 'other',
)

# ---------- 长文本切分参数 ----------
_CHUNK_SIZE = 2000       # 单 Chunk 最大字符数(取大块,减少 Chunk 数)
_CHUNK_OVERLAP = 200     # 相邻 Chunk 重叠
_MAX_CHUNKS = 3          # 取前 3 个 Chunk(约 6000 字)


def _load_prompt():
    """
    Sprint 8 新增:DB active 模板优先(bid_requirement),失败回退原文件解析逻辑。
    :return: (system_prompt, human_prompt_template)
    """
    # Sprint 8: DB active Prompt 优先
    try:
        from app.services import prompt_service
        tpl = prompt_service.get_active_template('bid_requirement')
        if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
            return tpl['system_prompt'], tpl['human_prompt']
    except Exception as _e:
        logger.warning('[Bid:extractor] PromptTemplate DB 查询失败,回退原 .md 文件: %s', _e)

    # ---------- Sprint 0~7 原逻辑(100% 保留,作为 fallback)----------
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Bid:extractor] Prompt 文件加载失败: %s', _PROMPT_FILE)
        return (
            '你是招投标文件结构化解析专家。从招标文件全文中提取 15 个核心字段,输出严格 JSON。'
            '禁止编造;未提取的字段填 null;数组字段未提取填 []。',
            '【招标文件全文】\n{bid_text}\n\n请提取 15 个核心字段,输出严格 JSON(无代码块包裹):'
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
        system_prompt = '你是招投标文件结构化解析专家,输出严格 JSON。'
    if not human_prompt:
        human_prompt = '【招标文件全文】\n{bid_text}\n\n请提取 15 个核心字段:'

    return system_prompt, human_prompt


def _truncate_text(text: str):
    """
    长文本截断(取前 ~6000 字) - Sprint 7.1 新增返回 chunks_metadata

    :return: (truncated_text, chunks_metadata)
        chunks_metadata: [{chunk_id, start_offset, end_offset, page_number, length}]
        用于后续字段来源匹配(field_sources)
    """
    if not text:
        return '', []
    if len(text) <= _CHUNK_SIZE * _MAX_CHUNKS:
        # 未切分时,生成一个整文本的元数据
        return text, [{
            'chunk_id': 'c0',
            'start_offset': 0,
            'end_offset': len(text),
            'page_number': 1,
            'length': len(text),
        }]

    chunks_metadata = []
    try:
        from app.knowledge.chunk import SemanticChunker
        chunker = SemanticChunker(chunk_size=_CHUNK_SIZE, overlap=_CHUNK_OVERLAP)
        chunks = chunker.split(text, None)
        if chunks:
            truncated_parts = []
            for i, c in enumerate(chunks[:_MAX_CHUNKS]):
                # SemanticChunker 的 chunk: c.text / c.metadata:{offset, page_number}
                meta = getattr(c, 'metadata', None) or {}
                start_off = int(meta.get('offset') or 0)
                page_num = int(meta.get('page_number') or 1)
                truncated_parts.append(c.text)
                chunks_metadata.append({
                    'chunk_id': f'c{i}',
                    'start_offset': start_off,
                    'end_offset': start_off + len(c.text),
                    'page_number': page_num,
                    'length': len(c.text),
                })
            truncated = '\n\n'.join(truncated_parts)
            logger.info('[Bid:extractor] 文本截断: original=%s chunks=%s truncated=%s',
                        len(text), len(chunks), len(truncated))
            return truncated, chunks_metadata
    except Exception:
        logger.exception('[Bid:extractor] SemanticChunker 切分失败,回退硬截断')

    # 回退:硬截断
    hard_cut = text[:_CHUNK_SIZE * _MAX_CHUNKS]
    chunks_metadata = [{
        'chunk_id': 'c0',
        'start_offset': 0,
        'end_offset': len(hard_cut),
        'page_number': 1,
        'length': len(hard_cut),
    }]
    return hard_cut, chunks_metadata


def _count_missing_fields(requirement_data: dict) -> tuple:
    """
    统计缺失字段数与已提取字段数
    - null / 空字符串 / 空数组 视为缺失

    :param requirement_data: 15 字段 dict
    :return: (field_count, missing_count)
    """
    if not requirement_data:
        return 0, len(_REQUIREMENT_FIELDS)

    missing = 0
    for field in _REQUIREMENT_FIELDS:
        val = requirement_data.get(field)
        if val is None:
            missing += 1
        elif isinstance(val, str) and not val.strip():
            missing += 1
        elif isinstance(val, list) and len(val) == 0:
            missing += 1

    field_count = len(_REQUIREMENT_FIELDS) - missing
    return field_count, missing


def extract_requirements(text: str) -> dict:
    """
    从招标文件全文中提取 15 个核心字段

    流程:
    1. 长文本截断(取前 ~6000 字)
    2. 加载 Prompt(bid_requirement_v1.md)
    3. 调用 call_deepseek
    4. 解析 JSON(容错)
    5. 计算 field_count / missing_count / confidence

    :param text: 招标文件全文(已清洗)
    :return: dict {
        requirement_data: {15 字段 + confidence},
        field_count, missing_count, confidence, error
    }
    """
    if not text or not text.strip():
        return {
            'requirement_data': None,
            'field_count': 0,
            'missing_count': len(_REQUIREMENT_FIELDS),
            'confidence': None,
            'error': '招标文件文本为空',
        }

    # ---------- 1. 长文本截断(Sprint 7.1:返回 chunks_metadata 用于字段来源追踪) ----------
    truncated_text, chunks_metadata = _truncate_text(text)

    # ---------- 2. 加载 Prompt ----------
    system_prompt, human_template = _load_prompt()
    human_prompt = human_template.format(bid_text=truncated_text)

    # ---------- 3. 调用 DeepSeek ----------
    # 局部 import(避免模块加载时强依赖 llm_client)
    from app.ai.agent.llm_client import call_deepseek

    # 15 字段 JSON 输出需要较多 token
    text_resp, error, error_type = call_deepseek(
        system_prompt, human_prompt, max_tokens=3000
    )

    if error:
        logger.warning('[Bid:extractor] LLM 调用失败: type=%s error=%s',
                       error_type, error)
        return {
            'requirement_data': None,
            'field_count': 0,
            'missing_count': len(_REQUIREMENT_FIELDS),
            'confidence': None,
            'error': error,
            'llm_error_type': error_type,
        }

    # ---------- 4. 解析 JSON ----------
    requirement_data = extract_json(text_resp)
    if requirement_data is None:
        logger.warning('[Bid:extractor] LLM 输出 JSON 解析失败: response_len=%s',
                        len(text_resp or ''))
        return {
            'requirement_data': None,
            'field_count': 0,
            'missing_count': len(_REQUIREMENT_FIELDS),
            'confidence': None,
            'error': 'LLM 输出 JSON 解析失败',
        }

    # ---------- 5. 计算质量指标 ----------
    field_count, missing_count = _count_missing_fields(requirement_data)
    # confidence 由 LLM 自评(0-1);非法值置 None
    confidence = requirement_data.get('confidence')
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        confidence = None

    logger.info('[Bid:extractor] 需求提取成功: fields=%s/15 missing=%s confidence=%s',
                field_count, missing_count, confidence)

    # ---------- 6. Sprint 7.1 新增:字段级来源追踪 ----------
    field_sources = _build_field_sources(requirement_data, truncated_text, chunks_metadata)

    return {
        'requirement_data': requirement_data,
        'field_count': field_count,
        'missing_count': missing_count,
        'confidence': confidence,
        'error': None,
        'field_sources': field_sources,
        'chunks_metadata': chunks_metadata,
    }


# ================================================================
# Sprint 7.1 新增:字段来源追踪工具
# ================================================================
def _flatten_field_value(val) -> list[str]:
    """
    把字段值压平成字符串列表(用于 source_text 匹配)
    - 标量 str/int/float/bool → [str(val)]
    - list → 递归逐项压平,拼接所有 leaf 值
    - dict → 递归压平 values()
    """
    if val is None:
        return []
    if isinstance(val, bool):
        return []
    if isinstance(val, (int, float)):
        s = str(val).strip()
        return [s] if len(s) >= 2 else []
    if isinstance(val, str):
        s = val.strip()
        return [s] if s and len(s) >= 2 else []
    if isinstance(val, list):
        out = []
        for item in val:
            out.extend(_flatten_field_value(item))
        return out
    if isinstance(val, dict):
        out = []
        for v in val.values():
            out.extend(_flatten_field_value(v))
        return out
    return []


def _find_source_text(snippets: list[str], full_text: str,
                      chunks_metadata: list[dict]) -> tuple[str, int, str, float]:
    """
    在 full_text 中寻找任一片段的出现位置,并返回
        (source_text, page_number, chunk_id, confidence)
    匹配策略:
    1. 最长的 snippet 精确优先(避免用单个 token 匹配)
    2. snippet 过长时截断为最大 80 字符匹配
    3. 匹配不到 → 返回空串 + page=0 + chunk_id 空
    confidence:基于 snippet 长度与匹配命中位置清晰度(0-1 经验值)
    """
    if not snippets or not full_text or not chunks_metadata:
        return '', 0, '', 0.0

    # 按 snippet 长度降序(长的特征更鲜明)
    sorted_snips = sorted(
        [s for s in dict.fromkeys(snippets) if len(s) >= 4],
        key=len, reverse=True,
    )[:8]
    if not sorted_snips:
        return '', 0, '', 0.0

    for snip in sorted_snips:
        # snippet 过长截断(避免 1 段几千字符无法精确匹配)
        search = snip[:120] if len(snip) > 120 else snip
        idx = full_text.find(search)
        if idx < 0:
            # 二次尝试:取中间 60 字符
            if len(snip) > 60:
                mid = len(snip) // 2
                search2 = snip[mid - 30:mid + 30]
                idx = full_text.find(search2)
                if idx >= 0:
                    search = search2
        if idx >= 0:
            # 计算命中 chunk 与 page
            chunk_id, page_num = _map_offset_to_chunk(idx, chunks_metadata)
            # 经验置信度:基于匹配片段长度,上限 0.95
            c = min(0.4 + min(len(search), 120) / 200.0, 0.95)
            # source_text:从命中位置扩展 +/-150 字符上下文
            ctx_start = max(0, idx - 100)
            ctx_end = min(len(full_text), idx + len(search) + 150)
            source_ctx = full_text[ctx_start:ctx_end]
            # 把 source_ctx 中的多余空白归一(减少 JSON 体积)
            source_ctx = ' '.join(source_ctx.split())
            return source_ctx, page_num, chunk_id, round(c, 4)
    return '', 0, '', 0.0


def _map_offset_to_chunk(offset: int, chunks_metadata: list[dict]) -> tuple[str, int]:
    """把 offset 映射到 chunk_id / page_number(线性遍历,chunks 通常 <=3)"""
    for c in chunks_metadata:
        start = int(c.get('start_offset') or 0)
        end = int(c.get('end_offset') or (start + int(c.get('length') or 0)))
        if start <= offset <= end:
            return c.get('chunk_id') or '', int(c.get('page_number') or 0)
    # 没命中 → 取最后一个 chunk
    last = chunks_metadata[-1] if chunks_metadata else {}
    return last.get('chunk_id') or '', int(last.get('page_number') or 0)


def _build_field_sources(requirement_data: dict,
                         full_text: str,
                         chunks_metadata: list[dict]) -> dict:
    """
    Sprint 7.1 新增:构建 15 字段的来源追踪

    :return: {field_name: {page_number, chunk_id, confidence, source_text}}
             - 缺失字段(null / 空数组)不参与匹配,值为 null
             - 匹配失败 → {page_number:0, chunk_id:'', confidence:0.0, source_text:''}
    """
    sources = {}
    if not requirement_data:
        return sources

    for field in _REQUIREMENT_FIELDS:
        val = requirement_data.get(field)
        # 缺失字段 → sources 中不提供或为 null
        if val is None:
            sources[field] = None
            continue
        if isinstance(val, str) and not val.strip():
            sources[field] = None
            continue
        if isinstance(val, list) and len(val) == 0:
            sources[field] = None
            continue

        snippets = _flatten_field_value(val)
        source_text, page_num, chunk_id, conf = _find_source_text(
            snippets, full_text, chunks_metadata
        )
        sources[field] = {
            'page_number': int(page_num or 0),
            'chunk_id': chunk_id,
            'confidence': conf,
            'source_text': source_text,
        }
    return sources
