"""
文档处理服务层(Service)
职责:文件保存 → 类型判断 → 文本提取(PDF/OCR)→ AI 字段提取编排。

迁移说明:
- extract_text_from_pdf:从 legacy/app.py 原样搬迁(行 334-366),pdfplumber 逻辑不变。
- process_upload:对应 legacy index() 的 POST 业务分支(行 555-659),但从 HTTP 上下文解耦——
  flash 消息以列表 [(category, message)] 返回,由 API 层回放,使 Service 可独立测试。

职责约束:本层不直接渲染模板、不访问 request 对象;仅编排 AI 层与工具层。

RC 修订:
- 将所有 print() 替换为 logger.info()/logger.debug(),统一日志输出渠道(SPRINT2_CODE_REVIEW B1)。
- 异常详情脱敏,避免内部错误信息泄露(SPRINT2_CODE_REVIEW B2)。
"""
import os
from werkzeug.utils import secure_filename
import pdfplumber
from flask import current_app

from app.utils.file_utils import get_file_type
from app.utils.text_utils import clean_text
from app.ai.ocr.ocr_service import extract_text_using_deepseek_ocr
from app.ai.llm.deepseek_service import extract_contract_fields
from app.extensions.logger import logger


def extract_text_from_pdf(pdf_path):
    """
    使用 pdfplumber 从 PDF 文件中提取文本内容
    (从 legacy/app.py 原样迁移,行 334-366)
    :param pdf_path: PDF 文件的完整路径
    :return: 提取到的文本内容字符串(已清理优化)
    """
    # 初始化空字符串用于存储提取的文本
    text = ""

    # 使用 with 语句打开 PDF 文件,确保文件正确关闭
    with pdfplumber.open(pdf_path) as pdf:
        # 获取 PDF 总页数
        total_pages = len(pdf.pages)
        logger.info("【PDF 解析】PDF 文件共 %s 页", total_pages)

        # 遍历 PDF 中的每一页
        for i, page in enumerate(pdf.pages):
            # 提取当前页面的文本
            page_text = page.extract_text()

            if page_text:  # 检查页面是否有文本内容
                logger.debug(
                    "【PDF 解析】第 %s 页提取到 %s 字符", i + 1, len(page_text)
                )
                # 清理页面文本后添加到总文本中
                cleaned_page_text = clean_text(page_text)
                text += cleaned_page_text + "\n\n"  # 每页之间添加两个空行分隔
            else:
                logger.debug("【PDF 解析】第 %s 页无文本内容", i + 1)

    # 对整体文本进行最终清理
    final_text = clean_text(text)
    logger.info("【PDF 解析】最终文本长度: %s 字符", len(final_text))

    return final_text


def process_upload(file):
    """
    处理上传文件业务:保存 → 类型判断 → 文本提取(PDF/OCR)→ AI 字段提取。
    对应 legacy index() 的 POST 业务分支,但从 HTTP 上下文解耦。

    :param file: werkzeug.datastructures.FileStorage
    :return: dict
        - text: 提取的文本
        - filename: 原始文件名(用于显示)
        - fields: 合同字段提取结果(dict 或 None)
        - ocr_method: 识别模式字符串
        - flashes: [(category, message), ...] 由 API 层回放为 flash
        - error: 异常信息(成功时为 None)
    """
    extracted_text = ""
    filename = ""
    contract_fields = None
    ocr_method = ""
    flashes = []

    # 保存文件(安全文件名 + 中文文件名回退唯一名)
    original_filename = file.filename
    safe_filename = secure_filename(file.filename)
    if not safe_filename:
        ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'pdf'
        safe_filename = f"upload_{os.urandom(8).hex()}.{ext}"
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_filename)
    filename = original_filename
    file_type = get_file_type(original_filename)

    try:
        # 保存上传的文件到指定目录
        file.save(file_path)
        flashes.append(('success', '文件上传成功！'))

        # 根据文件类型选择处理方式
        if file_type == 'pdf':
            # PDF 文件:仅使用 pdfplumber 提取文本,不使用 OCR
            logger.info("=" * 60)
            logger.info("【PDF 文件】使用 pdfplumber 提取文本")
            logger.info("=" * 60)
            extracted_text = extract_text_from_pdf(file_path)

            # 检查 pdfplumber 是否成功提取到文本
            if extracted_text.strip():
                logger.info("pdfplumber 文本提取成功")
                logger.info("当前识别模式:pdfplumber(PDF文本提取)")
                ocr_method = "pdfplumber"
                flashes.append(('success', 'PDF文本提取成功（pdfplumber）！'))
            else:
                # pdfplumber 提取失败,说明是扫描件
                logger.warning("pdfplumber 未能提取到文本,可能是扫描件")
                logger.info("当前识别模式:pdfplumber(无文本内容)")
                ocr_method = "pdfplumber"
                flashes.append(('warning', '当前 PDF 为扫描件，请上传图片版本或安装 Poppler 启用 PDF OCR'))
                extracted_text = ""
        else:
            # 图片文件(PNG/JPG/JPEG):使用 DeepSeek OCR
            logger.info("=" * 60)
            logger.info("【图片文件】使用 DeepSeek OCR 识别")
            logger.info("=" * 60)
            logger.info("OCR 识别中...")
            flashes.append(('info', 'OCR识别中...'))

            # 调用 DeepSeek OCR(只处理图片,不会处理 PDF)
            ocr_result = extract_text_using_deepseek_ocr(file_path, file_type)

            # 检查 OCR 是否成功
            if ocr_result and ocr_result.get('error') is None:
                extracted_text = ocr_result.get('text', '')
                pages = ocr_result.get('pages', 0)
                ocr_method = "DeepSeek OCR"
                logger.info("OCR 识别完成!共识别 %s 张图片", pages)
                logger.info("当前识别模式:DeepSeek OCR")
                flashes.append(('success', f'OCR识别完成！共识别 {pages} 张图片'))
            else:
                error_msg = ocr_result.get('error', '未知错误') if ocr_result else 'OCR 返回为空'
                logger.error("DeepSeek OCR 失败: %s", error_msg)
                flashes.append(('danger', f'OCR 识别失败：{error_msg}'))
                extracted_text = ""

        # AI 分析:检查是否成功获取文本,然后进行字段提取
        if extracted_text.strip():
            logger.info("=" * 60)
            logger.info("【第三步】开始 AI 合同字段分析")
            logger.info("=" * 60)
            flashes.append(('info', '正在使用 AI 分析合同...'))
            contract_fields = extract_contract_fields(extracted_text)

            # 检查是否成功提取字段
            if contract_fields and not contract_fields.get('error'):
                flashes.append(('success', 'AI 字段提取完成！'))
            else:
                error_msg = contract_fields.get('error', '未知错误') if contract_fields else '返回结果为空'
                flashes.append(('danger', f'AI 分析失败：{error_msg}'))
        else:
            flashes.append(('warning', '无法提取合同文本，请确认文件是有效的 PDF 或图片'))

    except Exception as e:
        # 捕获处理过程中的异常(详细堆栈记录到日志,对客户端仅返回通用提示)
        flashes.append(('danger', '处理文件时出错,请重试'))
        logger.exception('文件上传/处理失败')
        # 如果文件已保存,删除它
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                logger.warning('清理临时文件失败: %s', file_path)
        # 清空提取的文本
        extracted_text = ""
        ocr_method = ""
        return {
            'text': extracted_text,
            'filename': filename,
            'fields': contract_fields,
            'ocr_method': ocr_method,
            'flashes': flashes,
            'error': '文件处理失败',
        }

    return {
        'text': extracted_text,
        'filename': filename,
        'fields': contract_fields,
        'ocr_method': ocr_method,
        'flashes': flashes,
        'error': None,
    }


def analyze_document(file_path, file_type):
    """
    分析已落盘的合同文件(Sprint 2 - v0.4.0 新增)

    复用既有 AI 能力(extract_text_from_pdf / extract_text_using_deepseek_ocr /
    extract_contract_fields),不保存文件、不访问 request、不产生 flashes。

    供 contract_service.create_contract 调用:文件由调用方保存后传入路径,
    本函数仅负责"文本提取 → AI 字段提取"的编排。

    :param file_path: 已保存文件的绝对路径
    :param file_type: 'pdf' 或 'image'(由 get_file_type 判定)
    :return: dict
        - text: 提取的文本
        - fields: 合同字段(dict 或 None)
        - ocr_method: 识别模式字符串
        - error: 异常信息(成功时为 None)
    """
    text = ""
    fields = None
    ocr_method = ""
    error = None

    try:
        if file_type == 'pdf':
            # PDF 文件:使用 pdfplumber 提取文本(复用既有函数)
            text = extract_text_from_pdf(file_path)
            ocr_method = 'pdfplumber'
            if not text.strip():
                error = 'PDF 为扫描件或无文本内容,未提取到文本'
        else:
            # 图片文件:使用 DeepSeek OCR(复用既有函数)
            ocr_result = extract_text_using_deepseek_ocr(file_path, 'image')
            if ocr_result and ocr_result.get('error') is None:
                text = ocr_result.get('text', '')
                ocr_method = 'DeepSeek OCR'
            else:
                error = ocr_result.get('error', 'OCR 返回为空') if ocr_result else 'OCR 返回为空'

        # 有文本时进行 AI 字段提取(复用既有函数)
        if text.strip():
            fields = extract_contract_fields(text)
            if fields and fields.get('error'):
                # 字段提取返回了错误结构,保留 fields 但记录 warning
                logger.warning('AI 字段提取返回错误: %s', fields.get('error'))
        elif not error:
            error = '未提取到文本,跳过字段提取'

    except Exception as e:
        # 容错:任何 AI 层异常被捕获为 error,不抛出(由调用方决定如何处理)
        logger.exception('analyze_document 异常: file_path=%s', file_path)
        error = 'AI 分析处理失败'

    return {
        'text': text,
        'fields': fields,
        'ocr_method': ocr_method,
        'error': error,
    }
