"""
Sentence-Transformers Embedding(Sprint 4 - v0.6.0)

职责:
- 用 sentence-transformers 将文本转向量
- 默认模型:BAAI/bge-small-zh-v1.5(中文优化,512 维)
- 归一化向量(normalize_embeddings=True),配合 FAISS 内积索引 = 余弦相似度

设计说明:
- 懒加载:模型在首次调用时加载(避免 Flask 启动阻塞;首次触发模型下载)
- 本地物化下载:Windows 上 HuggingFace 默认缓存使用符号链接,普通用户无权创建会
  报 WinError 14007。本类通过 huggingface_hub.snapshot_download(local_dir=...)
  将模型文件物化为真实文件到 storage/models/<basename>/ 下,再从本地路径加载,
  彻底规避符号链接问题,同时支持离线运行(首次下载后不再访问 HF Hub)。
- 禁止调用 OpenAI Embedding(任务书约束)
- 编码失败抛异常,由 service 层捕获并标记 embedding_status=failed

复用:
- 与 Sprint 3 DeepSeek 调用一样,从 current_app.config 读取模型名(由 service 注入)
"""
import os
import numpy as np

from app.extensions.logger import logger
from .base import BaseEmbedding


def _resolve_local_model_dir(model_name: str, base_dir: str = None) -> str:
    """
    根据 HF 模型名推导本地物化目录:storage/models/<basename>/
    例:BAAI/bge-small-zh-v1.5 → storage/models/bge-small-zh-v1.5/

    :param model_name: HF 模型 repo id(如 BAAI/bge-small-zh-v1.5)
    :param base_dir: 可选根目录;默认 backend/storage/models/
    :return: 本地目录绝对路径
    """
    if base_dir is None:
        # backend/app/knowledge/embedding/ → 上 4 级 = backend
        here = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here))))
        base_dir = os.path.join(backend_dir, 'storage', 'models')
    basename = model_name.rsplit('/', 1)[-1] if '/' in model_name else model_name
    return os.path.join(base_dir, basename)


class SentenceTransformerEmbedding(BaseEmbedding):
    """sentence-transformers 文本向量化"""

    def __init__(self, model_name: str = 'BAAI/bge-small-zh-v1.5',
                 local_dir: str = None):
        """
        :param model_name: HF 模型 repo id
        :param local_dir: 本地物化目录(可选);默认自动推导 storage/models/<basename>/
        """
        self.model_name = model_name
        self.local_dir = local_dir or _resolve_local_model_dir(model_name)
        self._model = None  # 懒加载

    def _ensure_local_model(self) -> str:
        """
        确保模型文件已物化到本地目录,返回可加载的本地路径。
        - 若本地目录已有 config.json,直接返回(离线可用)
        - 否则用 snapshot_download(local_dir=...) 下载真实文件(无符号链接)
        :return: 本地模型目录路径
        """
        config_path = os.path.join(self.local_dir, 'config.json')
        if os.path.exists(config_path):
            logger.info('[Knowledge:embedding] 使用本地模型: %s', self.local_dir)
            return self.local_dir

        # 首次下载:物化为真实文件(规避 Windows 符号链接权限问题)
        try:
            from huggingface_hub import snapshot_download
        except ImportError as e:
            raise ImportError(
                'huggingface_hub 未安装,无法下载 Embedding 模型。'
                '请执行: pip install huggingface_hub'
            ) from e

        os.makedirs(self.local_dir, exist_ok=True)
        logger.info('[Knowledge:embedding] 首次下载模型: %s → %s(可能较慢)',
                    self.model_name, self.local_dir)
        snapshot_download(repo_id=self.model_name, local_dir=self.local_dir)
        return self.local_dir

    @property
    def model(self):
        """懒加载模型(首次访问时加载,首次触发模型下载)"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                logger.exception('[Knowledge:embedding] sentence-transformers 未安装')
                raise ImportError(
                    'sentence-transformers 未安装,无法生成 Embedding。'
                    '请执行: pip install sentence-transformers'
                ) from e
            local_path = self._ensure_local_model()
            logger.info('[Knowledge:embedding] 加载模型: %s', local_path)
            self._model = SentenceTransformer(local_path)
        return self._model

    @property
    def dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list, batch_size: int = None) -> np.ndarray:
        """
        批量编码文本(归一化)
        :param texts: 文本列表
        :param batch_size: 可选 batch 大小(Sprint 8.7 评估批量预取传 16;None=ST 默认)
        :return: np.ndarray, shape=(len(texts), dimension),float32,已归一化
        """
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        kwargs = {
            'normalize_embeddings': True,
            'show_progress_bar': False,
            'convert_to_numpy': True,
        }
        if batch_size is not None:
            kwargs['batch_size'] = batch_size
        vectors = self.model.encode(texts, **kwargs)
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        """
        编码单条查询(归一化)
        :param text: 查询文本
        :return: np.ndarray, shape=(dimension,),float32,已归一化
        """
        vector = self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return np.asarray(vector, dtype=np.float32)
