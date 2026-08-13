"""
Pipeline 编排器(Sprint 3 - v0.5.0)

职责:
- 按顺序执行 6 个 Stage
- 驱动 AnalysisTask 状态机:pending → running → success / failed
- 实时更新 task.current_stage(前端可轮询进度)
- 收集各 Stage 日志到 ctx.stages_log,最终写入 task.stages_log
- 同步执行(Sprint 3 不引入 Celery;在 HTTP 请求内完成)

执行规则:
- Stage 返回 success → 继续下一个 Stage
- Stage 返回 skipped → 继续下一个 Stage(记录 skipped)
- Stage 返回 failed → 终止 Pipeline,Task 标记 failed
- Stage 抛异常 → BaseStage.run 兜底转为 failed

失败处理:
- extract 失败 → 直接 failed(无文本无法继续)
  - 但若 extract 是 success 且文本为空,ocr 会接手
- ocr 失败 → failed
- clean / chunk 失败 → failed
- llm 失败 → failed(但已提取文本仍落库到 documents)
- save 失败 → failed

事务边界:
- runner 不直接 commit(由 analysis_service 控制事务)
- save_stage 用 flush 刷入,runner 在 success 后由 service commit
"""
from datetime import datetime
from typing import Optional

from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.ai.pipeline.stages import STAGE_CLASSES
from app.extensions.db import db
from app.extensions.logger import logger


def run_pipeline(ctx: PipelineContext) -> dict:
    """
    执行 Document Pipeline

    :param ctx: PipelineContext(已含 file_path / file_type / document / task)
    :return: dict
        - status: 'success' / 'failed'
        - current_stage: 最终 Stage
        - error: 失败原因(成功时为 None)
        - stages_log: 各 Stage 日志
    """
    task = ctx.task

    # ---------- 1. Task 进入 running ----------
    if task is not None:
        task.status = 'running'
        task.started_time = datetime.utcnow()
        task.current_stage = None
        task.stages_log = []
        db.session.flush()

    logger.info('[Pipeline] 开始执行: contract_id=%s document_id=%s',
                task.contract_id if task else None,
                task.document_id if task else None)

    # ---------- 2. 按顺序执行 Stage ----------
    final_status = 'success'
    final_error = None
    last_stage = None

    for StageClass in STAGE_CLASSES:
        stage: BaseStage = StageClass()
        last_stage = stage.name

        # 更新 current_stage(前端可看到当前执行到哪一步)
        if task is not None:
            task.current_stage = stage.name
            db.session.flush()

        logger.info('[Pipeline] >>> 执行 Stage: %s', stage.name)

        # 计时执行
        start_ts = datetime.utcnow()
        result: StageResult = stage.run(ctx)
        duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)

        # 记录日志
        ctx.add_stage_log(
            stage_name=stage.name,
            status=result.status,
            duration_ms=duration_ms,
            error=result.error,
            metadata=result.metadata,
        )
        if task is not None:
            task.stages_log = list(ctx.stages_log)  # 实时更新,前端轮询可见
            db.session.flush()

        logger.info('[Pipeline] <<< Stage %s: %s (%s ms)',
                    stage.name, result.status, duration_ms)

        # 失败则终止
        if result.is_failed:
            final_status = 'failed'
            final_error = result.error
            break

    # ---------- 3. 收尾 ----------
    if task is not None:
        task.status = final_status
        task.current_stage = last_stage
        task.finished_time = datetime.utcnow()
        if final_status == 'failed':
            task.error_message = final_error
        else:
            task.error_message = None
        db.session.flush()

    logger.info('[Pipeline] 执行完成: status=%s stage=%s error=%s',
                final_status, last_stage, final_error)

    return {
        'status': final_status,
        'current_stage': last_stage,
        'error': final_error,
        'stages_log': ctx.stages_log,
    }
