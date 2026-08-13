"""
合同结构化切分器(Sprint 8.6 - v1.0.0 RAG 质量优化)

职责:
- 针对合同文档识别条款结构(第X章 / 第X条 / X.X / Article X),按条款切分 Chunk
- 避免普通长度切分导致条款上下文断裂(如"第八条 付款方式"被从中间截断)
- 非合同文档 / 无结构文本 → 委托 fallback_chunker(默认 SemanticChunker)处理

切分策略:
1. 逐行扫描,识别合同结构边界(章节/条款/编号)
2. 每个条款 = 边界行(标题)+ 后续正文行,直至下一边界
3. 条款 <= chunk_size → 整条为一个 Chunk
4. 条款 > chunk_size → 按句号/分号二次切分为多个子 Chunk(均继承 clause_title metadata)
5. 全文无任何结构命中 → 委托 fallback_chunker.split(组合,非继承)

metadata 扩展:
- splitter: 'contract'
- clause_title: '第八条 付款方式'(边界行原文)
- clause_no: '8'(从边界行提取的编号;无法提取则为空串)

设计原则:
- 与 SemanticChunker 同接口:split(text, page_map) -> List[Chunk]
- offset 基于"全文累积字符数"计算,与 page_map 对齐,page_number 用 locate_page 定位
- 不依赖 embedding / vectorstore / DB
"""
import re
from typing import List, Optional

from app.knowledge.chunk.chunk import Chunk
from app.knowledge.chunk.base import BaseChunker
from app.knowledge.chunk.semantic_chunker import SemanticChunker, _estimate_tokens
from app.knowledge.parser import PageRange, locate_page


# ---------- 合同结构正则(行首匹配)----------
# 第X章(第一章 / 第1章),含标题正文
_CHAPTER_RE = re.compile(r'^第[一二三四五六七八九十百零两\d]+章')
# 第X条(第一条 / 第1条),含标题正文 — 合同核心条款标记
_CLAUSE_RE = re.compile(r'^第[一二三四五六七八九十百零两\d]+条')
# X.X 或 X.X.X 编号(行首,如 8.1 / 8.1.1)
_NUM_CLAUSE_RE = re.compile(r'^\d+\.\d+(?:\.\d+)?(?:[、．.\s])')
# Article X(英文合同)
_ARTICLE_RE = re.compile(r'^Article\s+\d+', re.IGNORECASE)
# 中文数字序号(一、二、三、…、十二、) — 中文文档常见章节编号(Sprint 8.6 增强)
# 要求:行首 + 中文数字 + 顿号(、),且整行长度合理(避免匹配到正文中的列举)
_CN_SECTION_RE = re.compile(r'^[一二三四五六七八九十]{1,3}、')

# 用于 auto 模式检测:统计全文结构命中数
_DETECT_PATTERNS = [_CHAPTER_RE, _CLAUSE_RE, _NUM_CLAUSE_RE, _ARTICLE_RE, _CN_SECTION_RE]

# 中文数字 → 阿拉伯数字(支持常见范围,用于 clause_no 提取)
_CN_NUM_MAP = {
    '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}


def _cn_to_arabic(cn: str) -> Optional[str]:
    """中文数字转阿拉伯数字字符串(支持 1-99;复杂数字返回 None)"""
    if not cn:
        return None
    if cn.isdigit():
        return cn
    # 简单处理:十、二十、十五、二十三 等
    if len(cn) == 1 and cn in _CN_NUM_MAP:
        return str(_CN_NUM_MAP[cn])
    if '十' in cn:
        parts = cn.split('十')
        tens = _CN_NUM_MAP.get(parts[0], 1) if parts[0] else 1
        ones = _CN_NUM_MAP.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return str(tens * 10 + ones)
    return None


def _extract_clause_no(line: str) -> str:
    """从条款标题行提取条款编号(如 '第八条' → '8';'8.1' → '8.1';'一、' → '1')"""
    m = re.match(r'^第([一二三四五六七八九十百零两\d]+)条', line)
    if m:
        return _cn_to_arabic(m.group(1)) or m.group(1)
    m = re.match(r'^第([一二三四五六七八九十百零两\d]+)章', line)
    if m:
        return _cn_to_arabic(m.group(1)) or m.group(1)
    m = re.match(r'^(\d+\.\d+(?:\.\d+)?)', line)
    if m:
        return m.group(1)
    m = re.match(r'^Article\s+(\d+)', line, re.IGNORECASE)
    if m:
        return m.group(1)
    # 中文数字序号(一、二、三、)
    m = re.match(r'^([一二三四五六七八九十]{1,3})、', line)
    if m:
        return _cn_to_arabic(m.group(1)) or m.group(1)
    return ''


def _is_structure_boundary(line: str) -> bool:
    """判断该行是否为合同结构边界(章节/条款/编号)"""
    stripped = line.strip()
    if not stripped:
        return False
    return any(p.match(stripped) for p in _DETECT_PATTERNS)


def count_contract_structures(text: str) -> int:
    """
    统计文本中合同结构边界命中数(供 auto 模式判定)。
    """
    if not text:
        return 0
    count = 0
    for line in text.split('\n'):
        if _is_structure_boundary(line):
            count += 1
    return count


class ContractStructureChunker(BaseChunker):
    """合同结构化切分器(按条款切分,超长条款二次句切)"""

    def __init__(self,
                 chunk_size: int = 800,
                 overlap: int = 0,
                 min_chunk_size: int = 120,
                 fallback_chunker: Optional[BaseChunker] = None,
                 doc_title: Optional[str] = None,
                 include_title_prefix: bool = True,
                 group_clauses: bool = False):
        if chunk_size <= 0:
            raise ValueError('chunk_size 必须大于 0')
        self.chunk_size = chunk_size
        self.overlap = overlap  # 仅对超长条款二次句切生效(上下文衔接)
        self.min_chunk_size = min_chunk_size
        # Sprint 8.8: chunk 上下文前缀(文档标题)
        self.doc_title = doc_title
        self.include_title_prefix = include_title_prefix
        # Sprint 8.8: 条款分组模式 —— 将连续条款合并为 ~chunk_size 的上下文窗口,
        # 每个条款保留标题(【第X条 标题】)作内联小标题;解决条款级小块上下文过窄问题。
        self.group_clauses = group_clauses
        # 组合(非继承)fallback;默认 SemanticChunker
        self.fallback_chunker = fallback_chunker if fallback_chunker is not None else SemanticChunker()

    def split(self, text: str, page_map: List[PageRange]) -> List[Chunk]:
        """
        切分合同文本为按条款组织的 Chunk 列表

        :param text: 全文
        :param page_map: 页区间映射(用于定位 chunk 页码)
        :return: list[Chunk]
        """
        if not text or not text.strip():
            return []

        # 1. 无任何合同结构 → 委托 fallback(完全原行为)
        if count_contract_structures(text) == 0:
            return self.fallback_chunker.split(text, page_map)

        # 2. 识别条款段:[(title, clause_no, start_offset, text)]
        segments = self._split_into_clauses(text)
        if not segments:
            return self.fallback_chunker.split(text, page_map)

        # Sprint 8.8: 条款分组模式 —— 连续条款合并为 ~chunk_size 的上下文窗口
        if self.group_clauses:
            segments = self._group_clauses(segments)

        # 3. 逐段产出 Chunk(超长段二次句切)
        chunks: List[Chunk] = []
        for title, clause_no, start_offset, seg_text in segments:
            seg_text = seg_text.strip()
            if not seg_text:
                continue
            if len(seg_text) <= self.chunk_size:
                self._emit(chunks, seg_text, start_offset, page_map, title, clause_no)
            else:
                # 超长条款:按句号/分号二次切分,每子块 <= chunk_size(带 overlap 上下文衔接)
                sub_pieces = self._split_long_clause(seg_text, self.chunk_size, self.overlap)
                for piece in sub_pieces:
                    piece = piece.strip()
                    if not piece:
                        continue
                    self._emit(chunks, piece, start_offset, page_map, title, clause_no)
                    # 后续子块 offset 推进(粗略,基于 piece 长度)
                    start_offset += len(piece)

        # 4. 过小 chunk 合并到前一个(避免碎片)
        chunks = self._merge_tiny(chunks)
        return chunks

    # ---------- 内部方法 ----------
    def _split_into_clauses(self, text: str) -> List[tuple]:
        """
        扫描全文,按结构边界切分为条款段。
        :return: [(title, clause_no, start_offset, seg_text)]
        """
        segments = []
        lines = text.split('\n')
        # 计算每行起始 offset(\n 计 1 字符)
        line_offsets = []
        cursor = 0
        for ln in lines:
            line_offsets.append(cursor)
            cursor += len(ln) + 1  # +1 for '\n'

        cur_title = ''
        cur_no = ''
        cur_start = None
        cur_lines: List[str] = []

        def flush(end_offset):
            if cur_start is None or not cur_lines:
                return
            seg_text = '\n'.join(cur_lines)
            if seg_text.strip():
                segments.append((cur_title, cur_no, cur_start, seg_text))

        for i, ln in enumerate(lines):
            # Sprint 8.8: 跳过 markdown 注释行(如 "# 用途: xxx"),
            # 注释不是合同正文,避免污染 chunk(offset 仍基于原文,page 定位不受影响)
            if ln.strip().startswith('#'):
                continue
            if _is_structure_boundary(ln):
                # 命中边界 → 先 flush 前一段
                flush(line_offsets[i])
                cur_title = ln.strip()
                cur_no = _extract_clause_no(ln)
                cur_start = line_offsets[i]
                cur_lines = [ln]
            else:
                if cur_start is None:
                    # 边界前的导言(无条款标题) — 作为 preamble 段
                    cur_title = '导言'
                    cur_no = ''
                    cur_start = line_offsets[i] if line_offsets else 0
                    cur_lines = [ln]
                else:
                    cur_lines.append(ln)
        # 收尾
        flush(cursor)
        return segments

    def _group_clauses(self, segments: List[tuple]) -> List[tuple]:
        """
        Sprint 8.8: 将连续条款段合并为 ~chunk_size 的上下文窗口。
        每个条款段保留标题(【标题】作内联小标题),合并后整体为一个 Chunk。
        返回与 _split_into_clauses 同构的 [(title, clause_no, start_offset, seg_text)]。
        """
        groups: List[tuple] = []
        cur_parts: List[str] = []
        cur_len = 0
        cur_start = None
        cur_title = ''
        cur_no = ''

        def _flush():
            nonlocal cur_parts, cur_len, cur_start, cur_title, cur_no
            if cur_start is None or not cur_parts:
                return
            groups.append((cur_title, cur_no, cur_start, '\n\n'.join(cur_parts)))
            cur_parts, cur_len, cur_start, cur_title, cur_no = [], 0, None, '', ''

        for title, clause_no, start_offset, seg_text in segments:
            seg_text = seg_text.strip()
            if not seg_text:
                continue
            # 将条款段格式化为【标题】\n正文(正文去除标题行,避免重复)
            body = seg_text
            if title and body.startswith(title):
                body = body[len(title):].lstrip('\n')
            if not body.strip():
                continue
            part = f'【{title}】\n{body.strip()}' if title else body.strip()
            if cur_start is None:
                cur_start = start_offset
                cur_title, cur_no = title, clause_no
            # 超过 chunk_size 且当前组非空 → 先 flush,再开启新组
            if cur_len > 0 and cur_len + len(part) > self.chunk_size:
                _flush()
                cur_start = start_offset
                cur_title, cur_no = title, clause_no
            cur_parts.append(part)
            cur_len += len(part)
        _flush()
        return groups

    def _split_long_clause(self, text: str, max_size: int, overlap: int = 0) -> List[str]:
        """超长条款按句号/分号切分为 <= max_size 的子块(overlap 携带前块末尾做上下文衔接)"""
        # 按中文/英文句号、分号、换行切分,保留分隔符
        parts = re.split(r'(?<=[。；;\n])', text)
        pieces = []
        cur = ''
        for p in parts:
            if not p:
                continue
            if len(cur) + len(p) <= max_size:
                cur += p
            else:
                if cur:
                    pieces.append(cur)
                # 单句就超长 → 硬切(步长 = max_size - overlap,保证窗口重叠)
                if len(p) > max_size:
                    step = max(1, max_size - overlap)
                    for j in range(0, len(p), step):
                        pieces.append(p[j:j + max_size])
                else:
                    # 新块携带上一块末尾 overlap 字符,保持语义连续
                    carry = cur[-overlap:] if (overlap > 0 and cur) else ''
                    cur = carry + p
        if cur:
            pieces.append(cur)
        return pieces

    def _emit(self, chunks: List[Chunk], text: str, start_offset: int,
              page_map: List[PageRange], clause_title: str, clause_no: str):
        """产出一个 Chunk,追加到 chunks 列表"""
        if not text or not text.strip():
            return
        body = text
        # Sprint 8.8: 前置上下文前缀(文档标题 + 条款标题),保证 chunk 自含
        # 合同名称/条款编号/标题/正文,避免孤立碎片(格式:【合同名称】【条款标题】正文)
        prefix_lines = []
        if self.include_title_prefix and self.doc_title:
            prefix_lines.append(f'【{self.doc_title}】')
        if self.include_title_prefix and clause_title:
            marker = f'【{clause_title}】'
            if body.startswith(clause_title) and not body.startswith(marker):
                # 条款标题已在正文首行 → 转为【标题】格式,避免重复
                body = body[len(clause_title):].lstrip('\n')
                prefix_lines.append(marker)
            elif not body.startswith(marker):
                # 分组模式:首个条款标题已以【标题】形式在正文中,不再重复
                prefix_lines.append(marker)
        if prefix_lines:
            body = '\n'.join(prefix_lines) + '\n' + body
        chunk = Chunk(
            text=body,
            chunk_index=len(chunks),
            page_number=locate_page(page_map, start_offset) if page_map else 0,
            start_offset=start_offset,
            end_offset=start_offset + len(text),
            token_count=_estimate_tokens(body),
            metadata={
                'splitter': 'contract',
                'clause_title': clause_title,
                'clause_no': clause_no,
            },
        )
        chunks.append(chunk)

    def _merge_tiny(self, chunks: List[Chunk]) -> List[Chunk]:
        """
        过小 chunk 合并到前一个(仅当同属一个条款,避免跨条款合并破坏结构边界)。
        合并条件:当前 chunk < min_chunk_size 且与前一个 chunk 同 clause_title
        且合并后不超 2×chunk_size。
        """
        if len(chunks) <= 1:
            return chunks
        merged: List[Chunk] = []
        for c in chunks:
            prev = merged[-1] if merged else None
            same_clause = (
                prev is not None
                and prev.metadata.get('clause_title') == c.metadata.get('clause_title')
                and prev.metadata.get('clause_no') == c.metadata.get('clause_no')
            )
            if (prev is not None and same_clause
                    and len(c.text) < self.min_chunk_size
                    and len(prev.text) + len(c.text) <= self.chunk_size * 2):
                prev.text = prev.text + '\n' + c.text
                prev.end_offset = c.end_offset
                prev.token_count = _estimate_tokens(prev.text)
            else:
                merged.append(c)
        # 重新编号 chunk_index
        for idx, c in enumerate(merged):
            c.chunk_index = idx
        return merged
