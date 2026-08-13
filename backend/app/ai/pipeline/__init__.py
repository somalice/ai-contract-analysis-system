"""
Document Pipeline 模块(Sprint 3 - v0.5.0)

企业级合同解析流水线,Stage 设计:
extract → ocr → clean → chunk → llm → save

对外只暴露 run_pipeline,内部由 runner 编排各 Stage。
"""
from app.ai.pipeline.context import PipelineContext
from app.ai.pipeline.runner import run_pipeline

__all__ = ['PipelineContext', 'run_pipeline']
