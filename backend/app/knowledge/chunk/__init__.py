"""
Chunk 包(Sprint 4 - v0.6.0 / Sprint 8.6 合同结构切分)

导出:
- Chunk:数据对象(含完整 metadata)
- BaseChunker:抽象基类
- SemanticChunker:语义切分实现(段落 + 长度 + overlap)
- ContractStructureChunker:合同结构化切分(Sprint 8.6)
- get_chunker:工厂函数(按 config.CHUNKER_MODE 选择)
- 默认切分参数
"""
from .chunk import Chunk
from .base import BaseChunker
from .semantic_chunker import (
    SemanticChunker,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    DEFAULT_MIN_CHUNK_SIZE,
)
from .contract_chunker import ContractStructureChunker, count_contract_structures
from .factory import get_chunker

__all__ = [
    'Chunk', 'BaseChunker', 'SemanticChunker',
    'ContractStructureChunker', 'get_chunker', 'count_contract_structures',
    'DEFAULT_CHUNK_SIZE', 'DEFAULT_OVERLAP', 'DEFAULT_MIN_CHUNK_SIZE',
]
