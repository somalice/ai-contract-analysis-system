"""
Knowledge 服务包(Sprint 4 - v0.6.0)

导出:
- vector_store_registry:组件单例注册表(embedding / vectorstore / retriever)
- knowledge_service:知识文档管理(上传/查询/删除)
- rag_service:RAG 问答编排
"""
# 注意:显式从子模块导入单例实例,避免 from . import vector_store_registry
# 拿到的是"模块对象"而非"实例"(两者同名)
from .vector_store_registry import vector_store_registry  # noqa: F401
from .knowledge_service import (  # noqa: F401
    upload_knowledge_document,
    get_knowledge_document_list,
    get_knowledge_document_detail,
    delete_knowledge_document,
)
from .rag_service import query_rag  # noqa: F401

__all__ = [
    'vector_store_registry',
    'upload_knowledge_document',
    'get_knowledge_document_list',
    'get_knowledge_document_detail',
    'delete_knowledge_document',
    'query_rag',
]
