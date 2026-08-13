"""
Chunk 数据对象(Sprint 4 - v0.6.0)

职责:
- 作为 chunker / vectorstore / retriever / service 之间传递 Chunk 的统一载体
- 解决 Sprint 3 Final Check 问题 1(Chunk 缺少 Metadata):
  含 page_number / start_offset / end_offset / token_count / metadata 全字段

设计说明:
- 纯数据对象(不含业务逻辑),便于跨层传递与序列化
- token_count 为估算值(中文按字符数/1.5 近似;Embedding 模型不强制要求精确 token)
- metadata 为 dict,预留扩展(段落序号 / 是否 overlap 内容 / 章节标题等)
- vector_id 在 vectorstore.add 后回写(初始为 None)
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    """
    知识 Chunk(切分产物,检索最小单元)

    :param text: Chunk 文本内容
    :param chunk_index: 文档内序号(从 0 开始)
    :param page_number: 来源页码(PDF;docx/txt 为 0)
    :param start_offset: 在全文中的起始字符偏移
    :param end_offset: 在全文中的结束字符偏移(不含)
    :param token_count: Token 估算数
    :param metadata: 扩展元信息(dict)
    :param vector_id: FAISS 向量 ID(vectorstore.add 后回写;初始 None)
    """
    text: str
    chunk_index: int
    page_number: int = 0
    start_offset: int = 0
    end_offset: int = 0
    token_count: int = 0
    metadata: dict = field(default_factory=dict)
    vector_id: Optional[int] = None

    def to_dict(self) -> dict:
        """转为 dict(用于序列化 / 落库)"""
        return {
            'text': self.text,
            'chunk_index': self.chunk_index,
            'page_number': self.page_number,
            'start_offset': self.start_offset,
            'end_offset': self.end_offset,
            'token_count': self.token_count,
            'metadata': self.metadata,
            'vector_id': self.vector_id,
        }

    def __repr__(self) -> str:
        return (
            f'<Chunk idx={self.chunk_index} page={self.page_number} '
            f'offset=[{self.start_offset},{self.end_offset}) '
            f'tokens={self.token_count} len={len(self.text)}>'
        )
