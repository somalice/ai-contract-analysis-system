"""
Pipeline 上下文(Sprint 3 - v0.5.0)

职责:
- 作为 Stage 之间数据传递的载体,Stage 之间不直接互相调用
- 承载 Document / AnalysisTask 模型实例,便于 Stage 回写中间产物
- 收集各 Stage 的执行日志,最终落库到 analysis_tasks.stages_log

设计原则(遵循用户规则 §9 Tool Design Rules):
- Stage 之间无直接依赖,仅通过 Context 共享数据
- Context 不包含业务逻辑,仅承载数据
- Stage 不得修改其他 Stage 的产物(只读 + 写自己的字段)
"""
from typing import Any, Optional


class PipelineContext:
    """
    Document Pipeline 执行上下文

    生命周期:由 analysis_service 创建 → 传给 runner → 依次传给各 Stage → 最终落库

    字段说明:
    - file_path / file_type:输入(已落盘文件)
    - document:Document 模型实例(extract/ocr Stage 回写 text_content)
    - task:AnalysisTask 模型实例(runner 回写 status/current_stage)
    - text:提取的文本(extract/ocr 产出)
    - chunks:文本切分块(chunk Stage 产出)
    - fields:LLM 提取的字段列表(llm Stage 产出)
    - stages_log:各 Stage 执行日志(runner 收集,最终写入 task.stages_log)
    """

    def __init__(self, file_path: str, file_type: str, document=None, task=None):
        # ---------- 输入 ----------
        self.file_path: str = file_path
        self.file_type: str = file_type  # 'pdf' 或 'image'
        self.document = document  # Document 模型实例
        self.task = task  # AnalysisTask 模型实例

        # ---------- Stage 产物 ----------
        self.text: str = ''  # 提取的全文
        self.chunks: list[str] = []  # 切分后的文本块
        self.fields: list[dict] = []  # LLM 提取的字段 [{name, value, confidence, source}]

        # ---------- 日志 ----------
        self.stages_log: list[dict] = []  # 各 Stage 执行日志

    def add_stage_log(self, stage_name: str, status: str,
                      duration_ms: int, error: Optional[str] = None,
                      metadata: Optional[dict] = None) -> None:
        """
        追加一条 Stage 执行日志
        :param stage_name: Stage 名称(extract / ocr / clean / chunk / llm / save)
        :param status: success / skipped / failed
        :param duration_ms: 执行耗时(毫秒)
        :param error: 失败原因(成功时为 None)
        :param metadata: Stage 产出的元信息(页数/Chunk 数/Token 数等)
        """
        self.stages_log.append({
            'stage': stage_name,
            'status': status,
            'duration_ms': duration_ms,
            'error': error,
            'metadata': metadata or {},
        })

    def __repr__(self) -> str:
        return (
            f'<PipelineContext file={self.file_type} '
            f'text_len={len(self.text)} chunks={len(self.chunks)} '
            f'fields={len(self.fields)}>'
        )
