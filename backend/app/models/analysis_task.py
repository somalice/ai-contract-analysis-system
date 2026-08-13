"""
分析任务模型(Sprint 3 - v0.5.0)

对应 analysis_tasks 表:
- id:主键
- task_no:任务编号(唯一,自动生成 AT-YYYYMMDDHHMMSS-XXXXXXXX)
- contract_id:外键 → contracts.id
- document_id:外键 → documents.id
- status:任务状态(pending / running / success / failed)
- current_stage:当前执行到的 Stage(extract / ocr / clean / chunk / llm / save)
- stages_log:各 Stage 执行日志(JSON 数组)
- error_message:失败原因(成功时为 None)
- triggered_by:触发者外键 → users.id
- started_time:开始执行时间
- finished_time:结束时间(成功 / 失败)
- created_time / updated_time:时间戳

关系:
- Contract → AnalysisTask 一对多(一个合同可多次分析)
- Document → AnalysisTask 一对多
- User → AnalysisTask 一对多(通过 backref,不修改 user.py)

状态机(单向推进):
pending → running → success
                   └→ failed

stages_log 结构示例:
[
  {"stage": "extract", "status": "success", "duration_ms": 320, "metadata": {"page_count": 5}},
  {"stage": "clean",   "status": "success", "duration_ms": 12,  "metadata": {"text_length": 4096}},
  {"stage": "llm",     "status": "failed",  "duration_ms": 8200, "error": "JSON 解析失败"}
]

设计说明:
- 任务化:每次分析独立可追踪,支持重跑(创建新 Task)
- 进度可查:current_stage + stages_log 让前端展示分析进度
- 同步执行:Sprint 3 不引入 Celery,Task 在 HTTP 请求内同步完成;
            但落库后前端可轮询查询状态(为 Sprint 4+ 异步化预留)
"""
from datetime import datetime
from app.extensions.db import db


class AnalysisTask(db.Model):
    """分析任务表(Document Pipeline 执行实例)"""
    __tablename__ = 'analysis_tasks'

    # ---------- 任务状态枚举 ----------
    # pending:已创建未执行(本阶段同步执行,pending 仅瞬时存在)
    # running:Pipeline 执行中
    # success:全部 Stage 成功
    # failed:某 Stage 失败(LLM 失败 / OCR 失败 / 无文本等)
    VALID_STATUSES = ('pending', 'running', 'success', 'failed')

    # ---------- Stage 枚举 ----------
    # 与 ai/pipeline/stages/ 下的 Stage 一一对应
    VALID_STAGES = ('extract', 'ocr', 'clean', 'chunk', 'llm', 'save')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    task_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'),
                            nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    current_stage = db.Column(db.String(32), nullable=True)
    stages_log = db.Column(db.JSON, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'),
                             nullable=True, index=True)
    started_time = db.Column(db.DateTime, nullable=True)
    finished_time = db.Column(db.DateTime, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    # Contract → AnalysisTask 一对多
    contract = db.relationship(
        'Contract',
        backref=db.backref('analysis_tasks', lazy='dynamic')
    )
    # triggered_by → User(通过 backref 在 User 上添加 triggered_tasks)
    trigger_user = db.relationship(
        'User',
        backref=db.backref('triggered_tasks', lazy='dynamic')
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_log=True):
        """
        转为 dict
        :param include_log: 是否包含 stages_log(列表场景可省略)
        :return: dict
        """
        return {
            'id': self.id,
            'task_no': self.task_no,
            'contract_id': self.contract_id,
            'document_id': self.document_id,
            'status': self.status,
            'current_stage': self.current_stage,
            'stages_log': self.stages_log if include_log else None,
            'error_message': self.error_message,
            'triggered_by': self.triggered_by,
            'started_time': self.started_time.strftime('%Y-%m-%d %H:%M:%S') if self.started_time else None,
            'finished_time': self.finished_time.strftime('%Y-%m-%d %H:%M:%S') if self.finished_time else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return f'<AnalysisTask {self.task_no} ({self.status})>'
