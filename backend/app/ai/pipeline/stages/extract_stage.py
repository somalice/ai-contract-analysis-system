"""
Extract Stage(Sprint 3 - v0.5.0)

职责:
- 从 PDF 文件提取文本(pdfplumber)
- 记录页数到 ctx.document
- 仅处理文本型 PDF;扫描件返回空文本(由 ocr_stage 兜底)

复用:services/document_service.extract_text_from_pdf(不重新开发 PDF 解析)
"""
from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.services.document_service import extract_text_from_pdf
from app.extensions.logger import logger


class ExtractStage(BaseStage):
    """PDF 文本提取 Stage"""

    @property
    def name(self) -> str:
        return 'extract'

    def should_run(self, ctx: PipelineContext) -> bool:
        # extract 始终执行(无论 pdf 还是 image;image 会在 ocr_stage 处理)
        # 但本 Stage 仅对 pdf 做文本提取,image 类型直接跳过让 ocr 处理
        return ctx.file_type == 'pdf'

    def _execute(self, ctx: PipelineContext) -> StageResult:
        logger.info('[Pipeline:extract] 开始 PDF 文本提取: %s', ctx.file_path)

        try:
            text = extract_text_from_pdf(ctx.file_path)
        except Exception as e:
            logger.exception('[Pipeline:extract] PDF 文本提取异常')
            return StageResult(StageResult.FAILED,
                               error=f'PDF 文本提取失败: {e}')

        # 统计页数(从 pdfplumber 重新打开统计,避免修改 extract_text_from_pdf 签名)
        page_count = 0
        try:
            import pdfplumber
            with pdfplumber.open(ctx.file_path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            # 页数统计失败不影响主流程
            logger.warning('[Pipeline:extract] 页数统计失败,置为 0')

        # 写入 ctx
        ctx.text = text
        # 回写 document 元信息(由 runner 统一 commit,这里只改内存对象)
        if ctx.document is not None:
            ctx.document.text_content = text
            ctx.document.text_length = len(text)
            ctx.document.page_count = page_count
            ctx.document.extract_method = 'pdfplumber' if text.strip() else 'none'

        metadata = {
            'page_count': page_count,
            'text_length': len(text),
            'method': 'pdfplumber',
            'has_text': bool(text.strip()),
        }
        logger.info('[Pipeline:extract] PDF 文本提取完成: 页数=%s 文本长度=%s',
                    page_count, len(text))

        # 注意:即使提取到空文本(扫描件),extract Stage 本身算 success
        # (它正确执行了 pdfplumber,只是 PDF 无文本层);
        # 空文本会触发 ocr_stage 的 should_run
        return StageResult(StageResult.SUCCESS, metadata=metadata)
