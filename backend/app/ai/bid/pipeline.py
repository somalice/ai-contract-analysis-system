"""
Bid Pipeline(Sprint 7 - v0.9.0)

职责:
- 招标文件 → 文本提取 → 文本清洗 → 需求提取 → 结构化 Requirement
- 复用 Sprint 3 低层函数(extract_text_from_pdf / extract_text_using_deepseek_ocr / clean_text)
- 不复用 analysis_service.trigger_analysis(contract-coupled,会建 ContractField)

Pipeline 阶段(对齐 Sprint 3 Stage 命名,但不创建 AnalysisTask):
1. extract:PDF 文本提取(pdfplumber)/ OCR(图片型 PDF)
2. clean:文本清洗(复用 Sprint 3 clean_text)
3. llm:DeepSeek 提取 15 字段 JSON(调 requirement_extractor)

复用清单(只读 import):
- extract_text_from_pdf → app.services.document_service
- extract_text_using_deepseek_ocr → app.ai.ocr.ocr_service
- clean_text → app.utils.text_utils

输出结构:
{
  text: str,                # 清洗后全文(供 BidDocument.text_content 落库)
  extract_method: str,      # pdfplumber / deepseek_ocr / none
  page_count: int,          # 页数(PDF)
  requirements: dict,       # extract_requirements 返回的结构
  error: str|null           # Pipeline 错误(成功为 None)
}

约束:
- 不创建 AnalysisTask(与 Sprint 3 表解耦)
- 失败返回 error,不抛异常(由 bid_service 决策 UPDATE 状态)
- 禁止 print() / return str(e)
"""
import os
from typing import Optional

from flask import current_app

from app.extensions.logger import logger

from .requirement_extractor import extract_requirements


# ---------- 文件类型常量 ----------
_FILE_TYPE_PDF = 'pdf'
_FILE_TYPE_IMAGE = 'image'


def _get_file_type(filename: str) -> str:
    """获取文件类型(pdf / image)"""
    if not filename or '.' not in filename:
        return _FILE_TYPE_PDF
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return _FILE_TYPE_PDF
    return _FILE_TYPE_IMAGE


def _count_pdf_pages(pdf_path: str) -> int:
    """
    统计 PDF 页数(用 pdfplumber,不改 Sprint 3)
    :param pdf_path: PDF 文件路径
    :return: 页数(失败返回 0)
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)
    except Exception:
        logger.exception('[Bid:pipeline] PDF 页数统计失败: %s', pdf_path)
        return 0


def _extract_text(file_path: str, file_type: str) -> dict:
    """
    文本提取(extract stage)
    - pdf:用 extract_text_from_pdf(pdfplumber)
    - image:用 extract_text_using_deepseek_ocr(DeepSeek Vision)

    :return: {text, extract_method, error}
    """
    # ---------- PDF 文本提取 ----------
    if file_type == _FILE_TYPE_PDF:
        try:
            from app.services.document_service import extract_text_from_pdf
            text = extract_text_from_pdf(file_path)
            if text and text.strip():
                return {'text': text, 'extract_method': 'pdfplumber', 'error': None}
            # PDF 无文本(扫描件)→ 尝试 OCR
            logger.info('[Bid:pipeline] PDF 无文本,尝试 OCR(扫描件)')
        except Exception:
            logger.exception('[Bid:pipeline] PDF 文本提取失败,尝试 OCR')
            # 不立即返回错误,继续尝试 OCR

    # ---------- OCR(图片 / 扫描型 PDF) ----------
    try:
        from app.ai.ocr.ocr_service import extract_text_using_deepseek_ocr
        # OCR 仅处理 image 类型;扫描型 PDF 需先转图片(本期不支持,返回空)
        ocr_result = extract_text_using_deepseek_ocr(file_path, file_type)
        text = ocr_result.get('text', '') if isinstance(ocr_result, dict) else ''
        if text and text.strip():
            return {'text': text, 'extract_method': 'deepseek_ocr', 'error': None}
        ocr_error = ocr_result.get('error') if isinstance(ocr_result, dict) else None
        return {
            'text': '',
            'extract_method': 'none',
            'error': ocr_error or '文本提取失败(PDF 无文本且 OCR 未识别到内容)',
        }
    except Exception:
        logger.exception('[Bid:pipeline] OCR 调用失败')
        return {
            'text': '',
            'extract_method': 'none',
            'error': 'OCR 调用异常',
        }


def run_bid_pipeline(file_path: str, file_name: str = '') -> dict:
    """
    执行 Bid Pipeline:文本提取 → 清洗 → 需求提取

    流程:
    1. 判断文件类型(pdf / image)
    2. extract:文本提取(pdfplumber / OCR)
    3. clean:文本清洗(复用 Sprint 3 clean_text)
    4. llm:调用 extract_requirements 提取 15 字段

    :param file_path: 招标文件路径
    :param file_name: 原始文件名(用于判断类型,可选)
    :return: dict {
        text, extract_method, page_count, requirements, error
    }
    """
    if not file_path or not os.path.exists(file_path):
        return {
            'text': '',
            'extract_method': 'none',
            'page_count': 0,
            'requirements': None,
            'error': '招标文件不存在',
        }

    file_type = _get_file_type(file_name or file_path)
    page_count = _count_pdf_pages(file_path) if file_type == _FILE_TYPE_PDF else 1

    # ---------- 1. extract ----------
    extract_result = _extract_text(file_path, file_type)
    raw_text = extract_result.get('text', '')
    extract_method = extract_result.get('extract_method', 'none')
    extract_error = extract_result.get('error')

    if extract_error or not raw_text or not raw_text.strip():
        logger.warning('[Bid:pipeline] 文本提取失败: method=%s error=%s',
                       extract_method, extract_error)
        return {
            'text': '',
            'extract_method': extract_method,
            'page_count': page_count,
            'requirements': None,
            'error': extract_error or '招标文件未提取到文本',
        }

    # ---------- 2. clean ----------
    try:
        from app.utils.text_utils import clean_text
        cleaned_text = clean_text(raw_text)
    except Exception:
        logger.exception('[Bid:pipeline] 文本清洗失败,使用原始文本')
        cleaned_text = raw_text

    logger.info('[Bid:pipeline] 文本提取完成: method=%s pages=%s text_len=%s',
                extract_method, page_count, len(cleaned_text))

    # ---------- 3. llm(需求提取) ----------
    requirements = extract_requirements(cleaned_text)

    return {
        'text': cleaned_text,
        'extract_method': extract_method,
        'page_count': page_count,
        'requirements': requirements,
        'error': None,
    }
