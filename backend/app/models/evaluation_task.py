"""
AI 评估异步任务模型(Sprint 8.6.1 - 评估执行异步化)

对应表 evaluation_tasks:POST /evaluation/run 创建异步任务,后台线程执行。
状态机: pending → running → success | failed

约束:
- 不修改已有业务表,仅新增本表(评估任务跟踪专用)
- 不改变 evaluation_reports / evaluation_summary.json 结构(兼容已有 summary/history 接口)
"""
import uuid
from datetime import datetime

from app.extensions.db import db

# 任务状态常量
TASK_PENDING = 'pending'
TASK_RUNNING = 'running'
TASK_SUCCESS = 'success'
TASK_FAILED = 'failed'

# 评估模式常量(与 API 层 MODE_MAP 对齐)
MODE_QUICK = 'quick'
MODE_STANDARD = 'standard'
MODE_FULL = 'full'


def _generate_task_id():
    """生成任务编号:EVALTASK-YYYYMMDDHHMMSS-XXXXXXXX"""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'EVALTASK-{timestamp}-{suffix}'


class EvaluationTask(db.Model):
    """AI 评估异步任务"""
    __tablename__ = 'evaluation_tasks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), unique=True, nullable=False, index=True, default=_generate_task_id)

    # 状态机: pending → running → success | failed
    status = db.Column(db.String(16), nullable=False, default=TASK_PENDING, index=True)

    # 进度(0-100) + 当前阶段标识
    progress = db.Column(db.Integer, nullable=False, default=0)
    current_stage = db.Column(db.String(64), nullable=False, default='creating')

    # 评估模式(quick 10题 / standard 51题 / full 51题+LLM Judge)
    evaluation_mode = db.Column(db.String(16), nullable=False, default=MODE_QUICK)
    sample_size = db.Column(db.Integer, nullable=True)
    use_llm_answer = db.Column(db.Boolean, nullable=False, default=False)

    # 完成后关联的报告编号(EvaluationReport.report_no)
    report_id = db.Column(db.String(64), nullable=True, index=True)

    # 失败原因
    error = db.Column(db.Text, nullable=True)

    # 时间戳
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 触发人
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    # ---------- 序列化 ----------
    def to_dict(self):
        return {
            'task_id': self.task_id,
            'status': self.status,
            'progress': self.progress,
            'stage': self.current_stage,
            'evaluation_mode': self.evaluation_mode,
            'sample_size': self.sample_size,
            'use_llm_answer': self.use_llm_answer,
            'report_id': self.report_id,
            'error': self.error,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
            'generated_by': self.generated_by,
        }

    def __repr__(self):
        return f'<EvaluationTask id={self.id} task_id={self.task_id} status={self.status}>'
