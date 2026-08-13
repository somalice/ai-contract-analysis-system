"""
Chunker 抽象基类(Sprint 4 - v0.6.0)

职责:
- 定义文本切分统一契约:全文 + page_map → list[Chunk]
- Chunk 含完整 metadata(page_number / start_offset / end_offset / token_count)

解耦:
- Chunker 不依赖 embedding / vectorstore / retriever
- 仅依赖 Chunk 数据对象 + parser 的 page_map
"""
from abc import ABC, abstractmethod
from typing import List

from app.knowledge.chunk.chunk import Chunk
from app.knowledge.parser import PageRange


class BaseChunker(ABC):
    """文本切分器抽象基类"""

    @abstractmethod
    def split(self, text: str, page_map: List[PageRange]) -> List[Chunk]:
        """
        切分文本为 Chunk 列表

        :param text: 全文(parser 产物)
        :param page_map: 页区间映射(parser 产物,用于定位 chunk 页码)
        :return: list[Chunk](chunk_index 从 0 开始连续编号)
        """
        raise NotImplementedError
