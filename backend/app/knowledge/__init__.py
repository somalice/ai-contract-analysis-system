"""
知识管理与 RAG 基础模块(Sprint 4 - v0.6.0)

职责:
- 建立企业级 Knowledge Layer
- 完成 RAG 基础能力:Loader → Chunk → Embedding → VectorStore → Retriever → DeepSeek

模块结构:
- loader/      文档加载(pdf/docx/txt → 文本 + 页码)
- parser/      文档解析编排(按扩展名选 loader)
- chunk/       Chunk 切分(带 metadata + overlap)
- embedding/   Embedding(sentence-transformers,BAAI/bge-small-zh-v1.5)
- vectorstore/ Vector Store(FAISS 封装,create/save/load/add/search/delete)
- retriever/   Retriever(TopK + Score Threshold,预留 Hybrid)
- prompts/     RAG Prompt(rag_answer.md)
- services/    业务编排(knowledge_service / rag_service)+ vector_store_registry
- api/         API(Blueprint:knowledge_bp + rag_bp)

解耦原则(DI,依赖注入):
- Embedding / VectorStore / Retriever 面向 base 抽象编程
- 通过构造函数注入依赖,不直接 import 具体实现
- Service 层是唯一知道具体实现的地方

约束:
- 禁止修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
- 禁止 Agent / LangGraph / Workflow / MCP / Redis / Celery / ES / Milvus / pgvector
- 仅使用 FAISS + sentence-transformers + DeepSeek
- 禁止调用 OpenAI Embedding
- 禁止 print() / return str(e)
"""

__all__ = []
