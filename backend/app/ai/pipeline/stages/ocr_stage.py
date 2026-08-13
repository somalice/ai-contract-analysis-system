"""
OCR Stage(Sprint 3 - v0.5.0)

职责:
- 对图片文件执行 OCR(DeepSeek Vision)
- 对扫描型 PDF(extract 提取为空)兜底:Sprint 3 不支持 PDF→图片转换,记录失败原因

复用:ai/ocr/ocr_service.extract_text_using_deepseek_ocr(不重新开发 OCR)

触发条件(should_run):
- image 文件:始终执行
- pdf 文件:仅当 extract Stage 提取文本为空时执行(扫描件兜底)
  - 但 Sprint 3 OCR 仅支持图片,故 PDF 扫描件会在此 Stage 失败(明确报错)
"""
from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.ai.ocr.ocr_service import extract_text_using_deepseek_ocr
from app.extensions.logger import logger


class OcrStage(BaseStage):
    """OCR Stage(图片识别 + 扫描件兜底)"""

    @property
    def name(self) -> str:
        return 'ocr'

    def should_run(self, ctx: PipelineContext) -> bool:
        # image 文件:始终执行 OCR
        if ctx.file_type == 'image':
            return True
        # pdf 文件:仅当 extract 提取为空时兜底
        if ctx.file_type == 'pdf' and not ctx.text.strip():
            return True
        return False

    def _execute(self, ctx: PipelineContext) -> StageResult:
        logger.info('[Pipeline:ocr] 开始 OCR: type=%s', ctx.file_type)

        # ---------- PDF 扫描件:Sprint 3 不支持 PDF→图片转换 ----------
        if ctx.file_type == 'pdf':
            # extract 失败(空文本)走到这里,但 OCR 不支持 PDF
            logger.warning('[Pipeline:ocr] PDF 为扫描件,但 OCR 仅支持图片(Sprint 3 限制)')
            return StageResult(StageResult.FAILED,
                               error='PDF 为扫描件,OCR 仅支持图片文件(Sprint 3 不支持 PDF 转图片)')

        # ---------- 图片文件:调用 DeepSeek Vision OCR ----------
        try:
            ocr_result = extract_text_using_deepseek_ocr(ctx.file_path, 'image')
        except Exception as e:
            logger.exception('[Pipeline:ocr] OCR 调用异常')
            return StageResult(StageResult.FAILED, error=f'OCR 调用失败: {e}')

        if not ocr_result:
            return StageResult(StageResult.FAILED, error='OCR 返回为空')

        if ocr_result.get('error'):
            return StageResult(StageResult.FAILED,
                               error=f'OCR 失败: {ocr_result.get("error")}')

        text = ocr_result.get('text', '')
        pages = ocr_result.get('pages', 0)

        # 写入 ctx(覆盖 extract 的空文本)
        ctx.text = text
        if ctx.document is not None:
            ctx.document.text_content = text
            ctx.document.text_length = len(text)
            ctx.document.page_count = pages
            ctx.document.extract_method = 'deepseek_ocr'

        metadata = {
            'pages': pages,
            'text_length': len(text),
            'method': 'deepseek_ocr',
            'has_text': bool(text.strip()),
        }
        logger.info('[Pipeline:ocr] OCR 完成: 页数=%s 文本长度=%s', pages, len(text))

        return StageResult(StageResult.SUCCESS, metadata=metadata)
