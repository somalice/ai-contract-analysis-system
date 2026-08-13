"""
Pipeline Stage 抽象基类(Sprint 3 - v0.5.0)

职责:
- 定义 Stage 统一契约:name / should_run / run
- 每个 Stage 职责单一,只做一件事(extract / ocr / clean / chunk / llm / save)
- Stage 之间通过 PipelineContext 传递数据,不直接互相调用

设计原则(遵循用户规则 §9 Tool Design Rules):
- Stage 无状态(不持有跨调用的状态)
- Stage 独立可测(可单独实例化并传入 Context 测试)
- Stage 可替换(未来可替换 LLM Stage 的实现而不影响其他 Stage)
"""
from abc import ABC, abstractmethod
from typing import Optional

from app.ai.pipeline.context import PipelineContext


class StageResult:
    """Stage 执行结果"""

    # 状态枚举
    SUCCESS = 'success'
    SKIPPED = 'skipped'  # 条件不满足,跳过(如 ocr Stage 在 extract 成功时跳过)
    FAILED = 'failed'

    def __init__(self, status: str, error: Optional[str] = None,
                 metadata: Optional[dict] = None):
        """
        :param status: success / skipped / failed
        :param error: 失败原因(仅 failed 时有值)
        :param metadata: Stage 产出的元信息(页数/Chunk 数/Token 数等)
        """
        self.status = status
        self.error = error
        self.metadata = metadata or {}

    @property
    def is_success(self) -> bool:
        return self.status == self.SUCCESS

    @property
    def is_skipped(self) -> bool:
        return self.status == self.SKIPPED

    @property
    def is_failed(self) -> bool:
        return self.status == self.FAILED

    def __repr__(self) -> str:
        return f'<StageResult {self.status}>'


class BaseStage(ABC):
    """
    Stage 抽象基类

    子类必须实现:
    - name: Stage 名称(与 AnalysisTask.VALID_STAGES 对应)
    - should_run(ctx): 是否执行该 Stage(条件执行,如 ocr 仅在 extract 失败时执行)
    - _execute(ctx): 实际执行逻辑(返回 StageResult)

    子类不应:
    - 直接修改 ctx.task / ctx.document 的状态(由 runner 统一管理)
    - 直接调用其他 Stage
    - 访问数据库(除 save_stage 外,其他 Stage 不碰 DB)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage 名称(extract / ocr / clean / chunk / llm / save)"""

    @abstractmethod
    def should_run(self, ctx: PipelineContext) -> bool:
        """
        判断是否执行该 Stage
        :return: True 执行,False 跳过(记录为 skipped)
        """

    @abstractmethod
    def _execute(self, ctx: PipelineContext) -> StageResult:
        """
        实际执行逻辑(子类实现)
        :return: StageResult
        """

    def run(self, ctx: PipelineContext) -> StageResult:
        """
        执行入口(由 runner 调用)
        - 先检查 should_run,若 False 直接返回 skipped
        - 包裹 _execute,捕获异常转为 failed(避免 Stage 异常炸掉进程)
        """
        if not self.should_run(ctx):
            return StageResult(StageResult.SKIPPED,
                               metadata={'reason': 'should_run=False'})
        try:
            return self._execute(ctx)
        except Exception as e:
            # Stage 内部未捕获的异常,这里兜底转为 failed
            # 详细堆栈由 Stage 内部 logger.exception 记录,这里只保留 message
            from app.extensions.logger import logger
            logger.exception('Stage %s 未捕获异常', self.name)
            return StageResult(StageResult.FAILED, error=str(e) or 'Stage 执行异常')
