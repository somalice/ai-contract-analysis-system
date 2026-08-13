"""
FAISS VectorStore(Sprint 4 - v0.6.0)

职责:
- 封装 FAISS 索引:create / save / load / add / search / delete
- 本地持久化:索引文件(.faiss)+ 元数据(.meta.json)
- 业务代码禁止直接操作 FAISS,必须经本类(任务书约束)

设计要点:
- 索引类型:IndexFlatIP(内积)+ IndexIDMap2(支持自定义 ID / remove_ids)
  + 归一化向量 → 内积 = 余弦相似度,score ∈ [0, 1](归一化后非负)
- vector_id 由本类分配(自增计数器,持久化在 meta.json),避免重启后 ID 冲突
- 维度懒构建:首次 add 时按向量实际维度建索引(避免初始化时触发 Embedding 模型加载)
- meta.json:{next_vector_id, dimension, vectors:[{vector_id, chunk_id, document_id}]}
  FAISS 不存原始文本,溯源信息靠 meta + DB(knowledge_chunks)

解耦:
- 通过构造函数接收 BaseEmbedding,不 import 具体 Embedding 类
- 不依赖 Retriever / Service / DB
"""
import os
import json
from typing import List, Tuple
import numpy as np

from app.extensions.logger import logger
from .base import BaseVectorStore


class FaissVectorStore(BaseVectorStore):
    """FAISS 向量库实现"""

    def __init__(self, index_dir: str, index_name: str = 'knowledge.faiss'):
        self.index_dir = index_dir
        self.index_name = index_name
        # 索引文件 / 元数据文件路径
        self._index_path = os.path.join(index_dir, index_name)
        self._meta_path = os.path.join(index_dir, index_name + '.meta.json')

        self._index = None          # faiss.IndexIDMap2[IndexFlatIP]
        self._dimension = None      # 向量维度
        self._next_vector_id = 0    # 下一个可分配的 vector_id
        # vector_id → {chunk_id, document_id} 映射(与 meta.json 同步)
        self._meta = {}             # {vector_id: {chunk_id, document_id}}

    # ---------- 路径属性 ----------
    @property
    def index_path(self) -> str:
        return self._index_path

    @property
    def meta_path(self) -> str:
        return self._meta_path

    # ---------- 大小 ----------
    @property
    def size(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal

    # ---------- 懒 import faiss ----------
    @staticmethod
    def _import_faiss():
        try:
            import faiss
            return faiss
        except ImportError as e:
            logger.exception('[Knowledge:vectorstore] faiss 未安装')
            raise ImportError(
                'faiss 未安装,无法操作向量库。请执行: pip install faiss-cpu'
            ) from e

    # ---------- 索引构建 ----------
    def _build_index(self, dim: int):
        """创建 IndexFlatIP + IndexIDMap2"""
        faiss = self._import_faiss()
        base = faiss.IndexFlatIP(dim)
        self._index = faiss.IndexIDMap2(base)
        self._dimension = dim
        logger.info('[Knowledge:vectorstore] 建立索引: dim=%s', dim)

    # ---------- 持久化 ----------
    def load(self) -> bool:
        """从磁盘加载索引 + 元数据;无文件返回 False"""
        if not (os.path.exists(self._index_path) and os.path.exists(self._meta_path)):
            logger.info('[Knowledge:vectorstore] 无已存索引,跳过加载: %s', self._index_path)
            return False

        faiss = self._import_faiss()
        try:
            self._index = faiss.read_index(self._index_path)
            with open(self._meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            self._dimension = meta_data.get('dimension')
            self._next_vector_id = meta_data.get('next_vector_id', 0)
            # 重建 vector_id → {chunk_id, document_id} 映射
            self._meta = {int(v['vector_id']): {
                'chunk_id': v.get('chunk_id'),
                'document_id': v.get('document_id'),
            } for v in meta_data.get('vectors', [])}
            logger.info('[Knowledge:vectorstore] 加载索引成功: size=%s dim=%s next_id=%s',
                        self.size, self._dimension, self._next_vector_id)
            return True
        except Exception:
            logger.exception('[Knowledge:vectorstore] 加载索引失败: %s', self._index_path)
            self._index = None
            self._meta = {}
            self._next_vector_id = 0
            return False

    def save(self) -> None:
        """持久化索引 + 元数据到磁盘"""
        if self._index is None:
            logger.warning('[Knowledge:vectorstore] 索引为空,跳过保存')
            return

        faiss = self._import_faiss()
        os.makedirs(self.index_dir, exist_ok=True)
        try:
            faiss.write_index(self._index, self._index_path)
            meta_data = {
                'next_vector_id': self._next_vector_id,
                'dimension': self._dimension,
                'vectors': [
                    {'vector_id': vid, 'chunk_id': v['chunk_id'], 'document_id': v['document_id']}
                    for vid, v in self._meta.items()
                ],
            }
            with open(self._meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            logger.info('[Knowledge:vectorstore] 保存索引: size=%s path=%s',
                        self.size, self._index_path)
        except Exception:
            logger.exception('[Knowledge:vectorstore] 保存索引失败: %s', self._index_path)
            raise

    # ---------- 写入 ----------
    def add(self, vectors: np.ndarray, chunk_ids: List[int],
            document_ids: List[int]) -> List[int]:
        """
        批量写入向量
        :return: 分配的 vector_id 列表
        """
        if vectors is None or len(vectors) == 0:
            return []

        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        n, dim = vectors.shape

        if n != len(chunk_ids) or n != len(document_ids):
            raise ValueError('vectors / chunk_ids / document_ids 数量不一致')

        # 首次写入:按维度建索引
        if self._index is None:
            self._build_index(dim)

        if dim != self._dimension:
            raise ValueError(f'向量维度不匹配: 期望 {self._dimension}, 实际 {dim}')

        # 分配 vector_id(自增)
        faiss = self._import_faiss()
        ids = np.array(
            [self._next_vector_id + i for i in range(n)],
            dtype=np.int64
        )
        self._index.add_with_ids(vectors, ids)

        # 记录元数据
        assigned_ids = []
        for i in range(n):
            vid = int(ids[i])
            self._meta[vid] = {
                'chunk_id': chunk_ids[i],
                'document_id': document_ids[i],
            }
            assigned_ids.append(vid)
        self._next_vector_id += n

        logger.info('[Knowledge:vectorstore] 写入 %s 条向量: ids=%s..%s',
                    n, assigned_ids[0], assigned_ids[-1])
        return assigned_ids

    # ---------- 检索 ----------
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        """
        检索 TopK
        :return: [(vector_id, score)] 按 score 降序
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        qv = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        if self._dimension is not None and qv.shape[1] != self._dimension:
            raise ValueError(f'查询向量维度不匹配: 期望 {self._dimension}, 实际 {qv.shape[1]}')

        k = min(top_k, self._index.ntotal)
        scores, ids = self._index.search(qv, k)

        results = []
        for score, vid in zip(scores[0], ids[0]):
            if vid < 0:
                continue  # FAISS 返回 -1 表示不足 K 个
            results.append((int(vid), float(score)))
        return results

    # ---------- 删除 ----------
    def delete(self, vector_ids: List[int]) -> int:
        """按 vector_id 删除向量(从索引 + meta 移除)"""
        if self._index is None or not vector_ids:
            return 0

        faiss = self._import_faiss()
        # 仅删除存在于 meta 中的(避免传入无效 ID)
        valid_ids = [int(vid) for vid in vector_ids if int(vid) in self._meta]
        if not valid_ids:
            return 0

        ids_to_remove = np.array(valid_ids, dtype=np.int64)
        selector = faiss.IDSelectorBatch(ids_to_remove)
        # remove_ids 返回删除的数量
        removed = self._index.remove_ids(selector)

        for vid in valid_ids:
            self._meta.pop(vid, None)

        logger.info('[Knowledge:vectorstore] 删除 %s 条向量: ids=%s',
                    removed, valid_ids)
        return int(removed)

    # ---------- 元数据查询 ----------
    def get_chunk_id(self, vector_id: int):
        """根据 vector_id 查 chunk_id(供 retriever 溯源)"""
        meta = self._meta.get(int(vector_id))
        return meta['chunk_id'] if meta else None

    def get_vector_ids_by_document(self, document_id: int) -> List[int]:
        """根据 document_id 查所有 vector_id(供删除知识文档时清理向量)"""
        return [vid for vid, m in self._meta.items() if m.get('document_id') == document_id]
