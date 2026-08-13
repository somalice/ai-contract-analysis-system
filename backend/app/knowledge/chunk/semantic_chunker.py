"""
语义切分器(Sprint 4 - v0.6.0)

职责:
- 将全文切分为带 metadata + overlap 的 Chunk
- 解决 Sprint 3 Final Check 三个问题中的两个:
  1. Chunk 缺少 Metadata → 每个 Chunk 含 page_number / start_offset / end_offset /
     token_count / metadata
  3. Chunk 无 Overlap → 切分时相邻 Chunk 有 overlap(默认 200 字符)

切分策略(递归字符切分,类 LangChain RecursiveCharacterTextSplitter 简化版):
1. 优先按段落(双换行 \n\n)切分
2. 超长段落按单换行 \n 切分
3. 仍超长按句号/分号等切分
4. 最后按 chunk_size 硬切分
5. 组装为 Chunk 时,若当前 chunk 长度 + 下一段落 > chunk_size,则封口;
   下一个 chunk 从"当前 chunk 末尾往前 overlap 字符"处开始(实现 overlap)

参数:
- chunk_size: 单 Chunk 最大字符数(默认 500,适合中文检索)
- overlap: 相邻 Chunk 重叠字符数(默认 200)
- min_chunk_size: 最小 Chunk 长度(小于此值合并到前一个,避免碎片)

设计说明:
- offset 基于"累积已切分字符数"计算,保证与全文 text 对齐
- page_number 通过 parser.locate_page(page_map, start_offset) 定位
- token_count 估算:中文字符按 1 token,英文按 0.67(字符数/1.5 近似)
"""
from typing import List

from app.knowledge.chunk.chunk import Chunk
from app.knowledge.chunk.base import BaseChunker
from app.knowledge.parser import PageRange, locate_page


# ---------- 默认切分参数 ----------
DEFAULT_CHUNK_SIZE = 500       # 单 Chunk 最大字符数(中文检索宜小)
DEFAULT_OVERLAP = 200          # 相邻 Chunk 重叠字符数
DEFAULT_MIN_CHUNK_SIZE = 100   # 最小 Chunk 长度(小于此合并到前一个)

# ---------- 分隔符优先级(递归切分)----------
_SEPARATORS = ['\n\n', '\n', '。', '!', '?', '.', '；', ';', ' ', '']


def _estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数(中文按 1 字 ≈ 1 token,英文/数字按 1.5 字符 ≈ 1 token)
    :param text: 文本
    :return: token 估算数
    """
    if not text:
        return 0
    # 统计中文字符数(非 ASCII 字母数字)
    cjk = sum(1 for c in text if ord(c) > 127)
    other = len(text) - cjk
    return cjk + max(0, int(other / 1.5))


def _split_with_separators(text: str, separator: str) -> List[str]:
    """按指定分隔符切分,保留分隔符在段尾"""
    if separator == '':
        # 硬切分:按 chunk_size 切
        return [text[i:i + 500] for i in range(0, len(text), 500)]
    parts = text.split(separator)
    # 保留分隔符(附在每段末尾,除最后一段)
    result = []
    for i, p in enumerate(parts[:-1]):
        result.append(p + separator)
    if parts[-1]:
        result.append(parts[-1])
    return result


def _recursive_split(text: str, chunk_size: int, separators: list) -> List[str]:
    """
    递归切分:按分隔符优先级切,直到每段 <= chunk_size
    :return: 切分后的段落列表(每段 <= chunk_size)
    """
    if len(text) <= chunk_size:
        return [text] if text else []

    for i, sep in enumerate(separators):
        if sep == '' or sep in text:
            parts = _split_with_separators(text, sep)
            if len(parts) == 1:
                continue
            # 递归处理每段(用更细的分隔符)
            result = []
            for part in parts:
                if len(part) <= chunk_size:
                    if part:
                        result.append(part)
                else:
                    result.extend(_recursive_split(part, chunk_size, separators[i:]))
            return [r for r in result if r]
    # 所有分隔符都切不动,硬切
    return _split_with_separators(text, '')


class SemanticChunker(BaseChunker):
    """语义切分器(段落 + 长度 + overlap)"""

    def __init__(self,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap: int = DEFAULT_OVERLAP,
                 min_chunk_size: int = DEFAULT_MIN_CHUNK_SIZE):
        if chunk_size <= 0:
            raise ValueError('chunk_size 必须大于 0')
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError('overlap 必须 >= 0 且 < chunk_size')
        if min_chunk_size < 0:
            raise ValueError('min_chunk_size 必须 >= 0')
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def split(self, text: str, page_map: List[PageRange]) -> List[Chunk]:
        """
        切分文本为带 metadata + overlap 的 Chunk

        位置模型:
        - segments 顺序拼接 == 全文(保留分隔符),故 ''.join(已消费 segments) == text[:pos]
        - pos:已消费的全文字符数(单调递增)
        - chunk_start:当前 chunk 在全文中的起始 offset

        :param text: 全文
        :param page_map: 页区间映射
        :return: list[Chunk]
        """
        if not text or not text.strip():
            return []

        # 1. 递归切分为段落单元(每段 <= chunk_size)
        segments = _recursive_split(text, self.chunk_size, list(_SEPARATORS))
        if not segments:
            return []

        # 2. 贪心组装 Chunk(累积长度 + overlap)
        chunks: List[Chunk] = []
        current_parts: List[str] = []
        current_len = 0
        chunk_start = 0   # 当前 chunk 起始 offset
        pos = 0            # 已消费全文字符数

        for seg in segments:
            seg_len = len(seg)
            # 超限且当前已有内容 → 封口产出
            if current_parts and current_len + seg_len > self.chunk_size:
                chunk_text = ''.join(current_parts)
                self._emit_chunk(chunks, chunk_text, chunk_start, page_map)

                # overlap:下一 chunk 从本 chunk 末尾往前 overlap 字符开始
                if self.overlap > 0 and len(chunk_text) > self.overlap:
                    overlap_text = chunk_text[-self.overlap:]
                    current_parts = [overlap_text]
                    current_len = len(overlap_text)
                    chunk_start = pos - self.overlap
                else:
                    current_parts = []
                    current_len = 0
                    chunk_start = pos

            # 累加当前段
            current_parts.append(seg)
            current_len += seg_len
            pos += seg_len

        # 3. 收尾:剩余内容产出
        if current_parts:
            chunk_text = ''.join(current_parts)
            # 过小尾 chunk 合并到前一个(若存在且合并后不超 2×chunk_size)
            if (chunks and len(chunk_text) < self.min_chunk_size
                    and len(chunks[-1].text) + len(chunk_text) <= self.chunk_size * 2):
                chunks[-1].text = chunks[-1].text + chunk_text
                chunks[-1].end_offset = chunk_start + len(chunk_text)
                chunks[-1].token_count = _estimate_tokens(chunks[-1].text)
            else:
                self._emit_chunk(chunks, chunk_text, chunk_start, page_map)

        return chunks

    @staticmethod
    def _emit_chunk(chunks: list, text: str, start: int, page_map: List[PageRange]):
        """产出一个 Chunk,追加到 chunks 列表"""
        if not text or not text.strip():
            return
        chunk = Chunk(
            text=text,
            chunk_index=len(chunks),
            page_number=locate_page(page_map, start) if page_map else 0,
            start_offset=start,
            end_offset=start + len(text),
            token_count=_estimate_tokens(text),
            metadata={
                'splitter': 'semantic',
                'overlap': text != text.strip(),  # 标记是否含 overlap 内容(粗略)
            },
        )
        chunks.append(chunk)
