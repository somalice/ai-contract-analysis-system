"""
Clean Stage(Sprint 3 - v0.5.0)

职责:
- 对提取的文本进行清洗(去多余空白、合并空行、规范化)
- 复用 utils/text_utils.clean_text

触发条件:ctx.text 非空
失败情况:理论上不应失败(clean_text 是纯字符串处理)
"""
from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.utils.text_utils import clean_text
from app.extensions.logger import logger


class CleanStage(BaseStage):
    """文本清洗 Stage"""

    @property
    def name(self) -> str:
        return 'clean'

    def should_run(self, ctx: PipelineContext) -> bool:
        # 有文本才清洗
        return bool(ctx.text.strip())

    def _execute(self, ctx: PipelineContext) -> StageResult:
        original_length = len(ctx.text)
        logger.info('[Pipeline:clean] 开始文本清洗: 原长度=%s', original_length)

        try:
            cleaned = clean_text(ctx.text)
        except Exception as e:
            logger.exception('[Pipeline:clean] 文本清洗异常')
            return StageResult(StageResult.FAILED, error=f'文本清洗失败: {e}')

        ctx.text = cleaned
        # 同步更新 document.text_content(清洗后的版本)
        if ctx.document is not None:
            ctx.document.text_content = cleaned
            ctx.document.text_length = len(cleaned)

        metadata = {
            'original_length': original_length,
            'cleaned_length': len(cleaned),
            'reduced': original_length - len(cleaned),
        }
        logger.info('[Pipeline:clean] 文本清洗完成: 新长度=%s 减少=%s',
                    len(cleaned), original_length - len(cleaned))

        return StageResult(StageResult.SUCCESS, metadata=metadata)
