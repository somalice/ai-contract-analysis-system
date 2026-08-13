"""
Loader 包(Sprint 4 - v0.6.0)

导出:
- BaseLoader / Page:抽象与数据对象
- PdfLoader / DocxLoader / TxtLoader:具体实现
"""
from .base import BaseLoader, Page
from .pdf_loader import PdfLoader
from .docx_loader import DocxLoader
from .txt_loader import TxtLoader

__all__ = ['BaseLoader', 'Page', 'PdfLoader', 'DocxLoader', 'TxtLoader']
