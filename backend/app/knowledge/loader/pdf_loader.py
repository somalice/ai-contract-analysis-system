"""
PDF Loader(Sprint 4 - v0.6.0)

职责:
- 用 pdfplumber 逐页提取 PDF 文本
- 保留页码信息(每页一个 Page,供 chunker 计算 page_number)

复用说明:
- 复用 Sprint 3 extract_stage 的 pdfplumber 调用方式(不 import Stage 类,
  Stage 与 PipelineContext 耦合;此处复用底层 pdfplumber 逻辑)
- 复用 app.utils.text_utils.clean_text 做基础清洗

约束:
- 仅处理文本型 PDF;扫描件返回空文本(不在此处 OCR,知识库暂不强依赖 OCR)
- 无文本页面跳过(返回空 Page,parser 统计 page_count 时仍计入)
"""
import pdfplumber

from app.utils.text_utils import clean_text
from app.extensions.logger import logger
from .base import BaseLoader, Page


class PdfLoader(BaseLoader):
    """PDF 文档加载器(pdfplumber)"""

    @property
    def supported_extensions(self) -> tuple:
        return ('pdf',)

    def load(self, file_path: str) -> list:
        pages = []
        try:
            with pdfplumber.open(file_path) as pdf:
                total = len(pdf.pages)
                logger.info('[Knowledge:pdf_loader] PDF 共 %s 页: %s', total, file_path)
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ''
                    # 基础清洗(去多余空白 / 规范化)
                    cleaned = clean_text(page_text)
                    pages.append(Page(page_number=i + 1, text=cleaned))
        except Exception as e:
            logger.exception('[Knowledge:pdf_loader] PDF 解析失败: %s', file_path)
            raise

        return pages
