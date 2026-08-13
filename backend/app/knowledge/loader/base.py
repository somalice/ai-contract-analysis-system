"""
Loader 抽象基类(Sprint 4 - v0.6.0)

职责:
- 定义文档加载统一契约:文件路径 → 文本 + 页码信息
- 保留页码信息(供 chunker 计算 chunk 的 page_number,支持引用溯源)

设计说明:
- load() 返回 list[Page]:每页一个元素,含 page_number + text
- 不在此处合并全文(parser 负责),保持 loader 职责单一
- 面向抽象编程,具体 loader(pdf/docx/txt)实现该接口

解耦:
- Loader 不依赖 chunker / embedding / vectorstore
- 仅依赖文件系统 + 文本提取工具(pdfplumber / python-docx)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class Page:
    """文档单页(或单段,docx/txt 视为单页)"""
    page_number: int   # 从 1 开始(0 保留给无页码场景)
    text: str          # 该页文本(已基本清洗)


class BaseLoader(ABC):
    """文档加载器抽象基类"""

    @property
    @abstractmethod
    def supported_extensions(self) -> tuple:
        """该 loader 支持的扩展名元组,如 ('pdf',)"""
        raise NotImplementedError

    @abstractmethod
    def load(self, file_path: str) -> List[Page]:
        """
        加载文档,返回页列表
        :param file_path: 文件绝对路径
        :return: list[Page](page_number 从 1 开始;docx/txt 返回单页 page_number=1)
        :raises: FileNotFoundError / OSError / 解析异常
        """
        raise NotImplementedError
