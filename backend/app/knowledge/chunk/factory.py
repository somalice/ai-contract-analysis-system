"""
Chunker 工厂(Sprint 8.6 - v1.0.0 RAG 质量优化)

职责:
- 根据配置模式(semantic / contract / auto)与文档特征,选择合适的 Chunker
- 保持向后兼容:默认 'auto' 模式对非合同文档回退 SemanticChunker(原行为)

模式:
- 'semantic': 强制使用 SemanticChunker(完全原行为)
- 'contract': 强制使用 ContractStructureChunker(合同结构切分)
- 'auto'(默认): 统计文本中合同结构命中数,
  >= CONTRACT_CHUNKER_AUTO_THRESHOLD(默认 3) → contract chunker
  否则 → semantic chunker

设计:
- 无 Flask 上下文时(如单元测试)默认 semantic,不抛错
- knowledge_type='contract' 时倾向使用 contract chunker(auto 模式下降低检测门槛)
"""
from typing import Optional

from app.knowledge.chunk.base import BaseChunker
from app.knowledge.chunk.semantic_chunker import SemanticChunker
from app.knowledge.chunk.contract_chunker import (
    ContractStructureChunker,
    count_contract_structures,
)


def _get_mode(mode: Optional[str]) -> str:
    """读取 CHUNKER_MODE 配置;无 Flask 上下文时默认 'auto'"""
    if mode:
        return mode.lower()
    try:
        from flask import current_app
        return current_app.config.get('CHUNKER_MODE', 'auto').lower()
    except Exception:
        return 'auto'


def _get_auto_threshold() -> int:
    """读取自动检测阈值;无 Flask 上下文时默认 3"""
    try:
        from flask import current_app
        return int(current_app.config.get('CONTRACT_CHUNKER_AUTO_THRESHOLD', 3))
    except Exception:
        return 3


def _make_contract_chunker(doc_title: Optional[str] = None) -> ContractStructureChunker:
    """按 config 构造 ContractStructureChunker(参数化 chunk_size/overlap/标题前缀)。

    Sprint 8.8: chunk 策略可配置,支持实验(评估/导入前覆盖 app.config 即可切换)。
    """
    size, overlap = 800, 0
    include_title = True
    group_clauses = False
    try:
        from flask import current_app
        size = int(current_app.config.get('CONTRACT_CHUNK_SIZE', 800))
        overlap = int(current_app.config.get('CONTRACT_CHUNK_OVERLAP', 0))
        include_title = bool(current_app.config.get('CONTRACT_CHUNK_INCLUDE_TITLE', True))
        group_clauses = bool(current_app.config.get('CONTRACT_CHUNK_GROUP_CLAUSES', False))
    except Exception:
        pass
    return ContractStructureChunker(
        chunk_size=size,
        overlap=overlap,
        min_chunk_size=120,
        doc_title=doc_title,
        include_title_prefix=include_title,
        group_clauses=group_clauses,
        fallback_chunker=SemanticChunker(),
    )


def get_chunker(filename: Optional[str] = None,
                text: Optional[str] = None,
                knowledge_type: Optional[str] = None,
                mode: Optional[str] = None,
                doc_title: Optional[str] = None) -> BaseChunker:
    """
    根据 config.CHUNKER_MODE 与文档特征返回合适的 Chunker

    :param filename: 文件名(预留,可用于扩展按扩展名决策)
    :param text: 全文(用于 auto 模式结构检测)
    :param knowledge_type: 知识类型(general/contract/bid/company/case/qualification)
    :param mode: 显式模式覆盖(优先于 config)
    :param doc_title: 文档标题(Sprint 8.8:注入 chunk 上下文前缀,增强检索语义)
    :return: BaseChunker 实例
    """
    m = _get_mode(mode)

    # semantic:完全原行为
    if m == 'semantic':
        return SemanticChunker()

    # contract:强制合同切分(带 semantic fallback 处理非合同/超长条款)
    if m == 'contract':
        return _make_contract_chunker(doc_title)

    # auto:自动检测
    threshold = _get_auto_threshold()
    # knowledge_type='contract' 时降低门槛(合同知识库大概率是合同文档)
    if knowledge_type == 'contract':
        threshold = max(1, threshold - 2)

    struct_count = count_contract_structures(text) if text else 0
    if struct_count >= threshold:
        return _make_contract_chunker(doc_title)
    return SemanticChunker()
