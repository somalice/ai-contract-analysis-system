"""
Pipeline Stages 包(Sprint 3 - v0.5.0)

6 个 Stage,职责单一,顺序执行:
1. extract  - PDF 文本提取(pdfplumber)
2. ocr      - OCR 兜底(DeepSeek Vision,仅 extract 失败时)
3. clean    - 文本清洗
4. chunk    - 文本切分
5. llm      - LLM 结构化字段提取(8 字段 JSON)
6. save     - 字段落库(ContractField)
"""
from app.ai.pipeline.stages.extract_stage import ExtractStage
from app.ai.pipeline.stages.ocr_stage import OcrStage
from app.ai.pipeline.stages.clean_stage import CleanStage
from app.ai.pipeline.stages.chunk_stage import ChunkStage
from app.ai.pipeline.stages.llm_stage import LlmStage
from app.ai.pipeline.stages.save_stage import SaveStage

# 按执行顺序排列(runner 按此顺序遍历)
STAGE_CLASSES = (
    ExtractStage,
    OcrStage,
    CleanStage,
    ChunkStage,
    LlmStage,
    SaveStage,
)

__all__ = [
    'ExtractStage', 'OcrStage', 'CleanStage',
    'ChunkStage', 'LlmStage', 'SaveStage',
    'STAGE_CLASSES',
]
