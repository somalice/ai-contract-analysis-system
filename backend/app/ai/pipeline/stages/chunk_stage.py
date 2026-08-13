"""
Chunk Stage(Sprint 3 - v0.5.0)

职责:
- 将清洗后的文本切分为多个 Chunk,避免超长文本超过 LLM token 限制
- 切分策略:按段落(双换行)分割,超长段落按字符数二次切分

设计说明:
- Sprint 3 不引入 LangChain TextSplitter(避免过度工程化)
- 简单按段落 + 长度上限切分,满足 LLM 输入约束即可
- 当前 LLM Stage 将所有 Chunk 合并发给模型(合同文本通常 < 8K token);
  若超长则只取前 N 个 Chunk(记录 warning)

触发条件:ctx.text 非空
"""
from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.extensions.logger import logger


# ---------- 切分参数 ----------
# 单 Chunk 最大字符数(中文约 2000 字,对应 ~3000 token,DeepSeek 上下文充裕)
MAX_CHUNK_LENGTH = 2000
# 发送给 LLM 的最大总字符数(避免超 token;DeepSeek-chat 上下文 32K,留足输出空间)
MAX_TOTAL_LENGTH_FOR_LLM = 12000


class ChunkStage(BaseStage):
    """文本切分 Stage"""

    @property
    def name(self) -> str:
        return 'chunk'

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(ctx.text.strip())

    def _execute(self, ctx: PipelineContext) -> StageResult:
        text = ctx.text
        logger.info('[Pipeline:chunk] 开始文本切分: 文本长度=%s', len(text))

        try:
            chunks = self._split_text(text)
        except Exception as e:
            logger.exception('[Pipeline:chunk] 文本切分异常')
            return StageResult(StageResult.FAILED, error=f'文本切分失败: {e}')

        # 控制发送给 LLM 的总长度(超长截断)
        truncated = False
        if sum(len(c) for c in chunks) > MAX_TOTAL_LENGTH_FOR_LLM:
            kept = []
            total = 0
            for c in chunks:
                if total + len(c) > MAX_TOTAL_LENGTH_FOR_LLM:
                    break
                kept.append(c)
                total += len(c)
            truncated = True
            logger.warning('[Pipeline:chunk] 文本超长(%s 字符),截断为 %s 字符发送 LLM',
                           sum(len(c) for c in chunks), total)
            chunks = kept

        ctx.chunks = chunks

        metadata = {
            'chunk_count': len(chunks),
            'total_length': sum(len(c) for c in chunks),
            'max_chunk_length': max((len(c) for c in chunks), default=0),
            'truncated': truncated,
        }
        logger.info('[Pipeline:chunk] 切分完成: %s 个 Chunk', len(chunks))

        return StageResult(StageResult.SUCCESS, metadata=metadata)

    @staticmethod
    def _split_text(text: str) -> list:
        """
        切分策略:
        1. 按双换行(段落)分割
        2. 超长段落按 MAX_CHUNK_LENGTH 二次切分
        3. 过滤空段落
        """
        if not text:
            return []

        # 按段落分割(双换行或更多)
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        chunks = []
        for para in paragraphs:
            if len(para) <= MAX_CHUNK_LENGTH:
                chunks.append(para)
            else:
                # 超长段落按 MAX_CHUNK_LENGTH 二次切分
                for i in range(0, len(para), MAX_CHUNK_LENGTH):
                    piece = para[i:i + MAX_CHUNK_LENGTH].strip()
                    if piece:
                        chunks.append(piece)

        return chunks
