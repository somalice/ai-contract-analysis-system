"""
Save Stage(Sprint 3 - v0.5.0)

职责:
- 将 LLM 提取的字段落库到 contract_fields 表
- 每字段一行,含 confidence / source_text
- 同任务同字段唯一约束((contract_id, field_name, task_id))

触发条件:LLM Stage 已执行(无论字段是否全 null,都落库以便审计)
失败情况:DB 写入失败

设计说明:
- 本 Stage 是唯一访问数据库的 Stage(其他 Stage 只处理内存数据)
- 字段为空(value=null)也写入,记录"已尝试提取但未找到"(confidence=0.0)
- 写入前清理同任务旧字段(支持重跑;虽然 task 是新建的,防御性清理)
"""
from app.ai.pipeline.base import BaseStage, StageResult
from app.ai.pipeline.context import PipelineContext
from app.extensions.db import db
from app.models.contract_field import ContractField
from app.extensions.logger import logger


class SaveStage(BaseStage):
    """字段落库 Stage"""

    @property
    def name(self) -> str:
        return 'save'

    def should_run(self, ctx: PipelineContext) -> bool:
        # LLM Stage 已执行(ctx.fields 非空列表,即使全 null 字段也落库)
        # 必须有 task 和 contract 上下文
        return ctx.task is not None and ctx.fields is not None

    def _execute(self, ctx: PipelineContext) -> StageResult:
        logger.info('[Pipeline:save] 开始字段落库: %s 个字段', len(ctx.fields))

        contract_id = ctx.task.contract_id
        task_id = ctx.task.id

        try:
            # 防御性清理:同任务旧字段(正常情况下 task 是新建的,无旧数据)
            ContractField.query.filter_by(
                contract_id=contract_id, task_id=task_id
            ).delete(synchronize_session=False)

            # 批量插入
            for f in ctx.fields:
                field = ContractField(
                    contract_id=contract_id,
                    task_id=task_id,
                    field_name=f.get('name'),
                    field_value=f.get('value'),
                    confidence=float(f.get('confidence') or 0.0),
                    source_text=f.get('source'),
                )
                db.session.add(field)

            db.session.flush()  # 刷入但不提交(runner 统一 commit)

        except Exception as e:
            db.session.rollback()
            logger.exception('[Pipeline:save] 字段落库失败')
            return StageResult(StageResult.FAILED, error=f'字段落库失败: {e}')

        # 统计
        found_count = sum(1 for f in ctx.fields if f.get('value'))

        metadata = {
            'saved_count': len(ctx.fields),
            'found_count': found_count,
            'null_count': len(ctx.fields) - found_count,
        }
        logger.info('[Pipeline:save] 字段落库完成: 已保存 %s 个(其中 %s 个有值)',
                    len(ctx.fields), found_count)

        return StageResult(StageResult.SUCCESS, metadata=metadata)
