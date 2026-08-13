"""
向量库组件注册表(Sprint 4 - v0.6.0)

职责:
- 维护 Embedding / VectorStore / Retriever 的单例(进程内共享)
- 在 create_app 启动时加载已存在的 FAISS 索引
- 为 knowledge_service / rag_service 提供已配置的组件实例

设计说明:
- 单例:FAISS 索引在内存中,必须全进程共享(否则每次请求重建会丢失数据)
- Embedding 模型懒加载(首次 encode 时加载,避免启动阻塞)
- 组件通过依赖注入组装(vectorstore ← embedding;retriever ← vectorstore + embedding)
- 配置来自 current_app.config(在 app context 内访问)

约束:
- 业务代码(service / api)通过本 registry 获取组件,不直接实例化
- 不破坏 Sprint 0~3 任何既有架构
"""
import os
import threading

from flask import current_app

from app.extensions.logger import logger
from app.knowledge.embedding import SentenceTransformerEmbedding
from app.knowledge.vectorstore import FaissVectorStore
from app.knowledge.retriever import DenseRetriever


class _VectorStoreRegistry:
    """组件单例注册表(线程安全懒加载)"""

    def __init__(self):
        self._lock = threading.Lock()
        self._embedding = None
        self._vectorstore = None
        self._retriever = None
        self._initialized = False

    # ---------- 初始化 / 加载 ----------
    def load(self, app) -> bool:
        """
        在 create_app 启动时调用:创建 vectorstore 并加载已存索引
        :param app: Flask app(用于读取 config)
        :return: True 加载成功;False 无文件或失败
        """
        with self._lock:
            try:
                vector_store_dir = app.config['VECTOR_STORE_DIR']
                index_name = app.config['VECTOR_INDEX_NAME']
                os.makedirs(vector_store_dir, exist_ok=True)

                # 创建 embedding(不加载模型,懒加载)
                model_name = app.config.get('EMBEDDING_MODEL', 'BAAI/bge-small-zh-v1.5')
                self._embedding = SentenceTransformerEmbedding(model_name=model_name)

                # 创建 vectorstore 并加载已存索引
                self._vectorstore = FaissVectorStore(
                    index_dir=vector_store_dir,
                    index_name=index_name,
                )
                loaded = self._vectorstore.load()

                # 创建 retriever(DI 注入 vectorstore + embedding)
                self._retriever = DenseRetriever(
                    vectorstore=self._vectorstore,
                    embedding=self._embedding,
                    top_k=app.config.get('RETRIEVER_TOP_K', 5),
                    score_threshold=app.config.get('RETRIEVER_SCORE_THRESHOLD', 0.35),
                )

                self._initialized = True
                logger.info('[Knowledge:registry] 初始化完成 | 索引已加载=%s | 目录=%s',
                            loaded, vector_store_dir)
                return loaded
            except Exception:
                logger.exception('[Knowledge:registry] 初始化失败')
                # 不抛出:允许应用启动,首次上传时会重建
                self._initialized = False
                return False

    def _ensure_initialized(self):
        """确保已初始化(在请求上下文内懒初始化,兜底启动时失败的场景)"""
        if self._initialized and self._vectorstore is not None:
            return
        with self._lock:
            if self._initialized and self._vectorstore is not None:
                return
            # 兜底:用 current_app.config 初始化
            self.load(current_app)

    # ---------- 访问器 ----------
    @property
    def embedding(self):
        self._ensure_initialized()
        return self._embedding

    @property
    def vectorstore(self):
        self._ensure_initialized()
        return self._vectorstore

    @property
    def retriever(self):
        self._ensure_initialized()
        return self._retriever


# 全局单例(供 create_app / service 使用)
vector_store_registry = _VectorStoreRegistry()
