"""
合同审核报告模型(Sprint 5 - v0.7.0 / v0.7.1 增强)

对应 review_reports 表:
- id:主键
- review_no:审核编号(唯一,自动生成 RV-YYYYMMDDHHMMSS-XXXXXXXX)
- contract_id:外键 → contracts.id(审核的合同)
- task_id:外键 → analysis_tasks.id(基于哪次分析的字段,null=无分析,降级 legacy)
- status:任务状态(pending / running / success / failed)
- risk_level:整体风险等级(high / medium / low / none,成功时填)
- summary:审核总结(LLM 生成 / 兜底规则生成)
- risks:风险详情数组(JSON,结构见 SPRINT5_ANALYSIS §6.2)
- tool_calls_log:Agent 工具调用轨迹(JSON 数组,审计用)
- agent_trace:Agent 执行 Trace(JSON 数组,v0.7.1 新增,每步 thought/decision/action/observation)
- trace_summary:Trace 汇总统计(JSON,v0.7.1 新增,含 steps/总耗时/LLM耗时/Tool耗时)
- iterations:Agent ReAct 循环迭代次数
- llm_error:LLM 失败原因(成功为 null)
- llm_error_type:LLM 错误分类(v0.7.1 新增:timeout/rate_limit/server_error/network/auth/framework/json_parse/unknown)
- error_message:整体失败原因(成功为 null)
- triggered_by:触发者外键 → users.id
- started_time:开始执行时间
- finished_time:结束时间(成功 / 失败)
- created_time / updated_time:时间戳

v0.7.1 增强(Sprint 5 Final):
- 新增 agent_trace JSON 字段(向后兼容,旧数据为 null)
- 新增 trace_summary JSON 字段
- 新增 llm_error_type 字段
- 不修改既有字段,不破坏已有数据

关系:
- Contract → ReviewReport 一对多(一个合同可多次审核)
- AnalysisTask → ReviewReport 一对多(一次分析的字段可被多次审核;通过 backref,不修改 analysis_task.py)
- User → ReviewReport 一对多(通过 backref,不修改 user.py)

状态机(单向推进,与 AnalysisTask 一致):
pending → running → success
                   └→ failed

设计说明:
- 任务化:每次审核独立可追踪,支持重审(创建新 ReviewReport)
- 同步执行:Sprint 5 不引入 Celery,Agent 在 HTTP 请求内同步完成
- 不新增审批表 / 流程表 / 版本表(仅此 1 表)
- 不修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
- v0.7.1: agent_trace / trace_summary / llm_error_type 为新增字段,旧数据 null(向后兼容)
"""
from datetime import datetime
from app.extensions.db import db


class ReviewReport(db.Model):
    """合同审核报告表(Contract Review Agent 执行实例)"""
    __tablename__ = 'review_reports'

    # ---------- 任务状态枚举 ----------
    VALID_STATUSES = ('pending', 'running', 'success', 'failed')

    # ---------- 风险等级枚举 ----------
    VALID_RISK_LEVELS = ('high', 'medium', 'low', 'none')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    review_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('analysis_tasks.id'),
                        nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    risk_level = db.Column(db.String(32), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    risks = db.Column(db.JSON, nullable=True)
    tool_calls_log = db.Column(db.JSON, nullable=True)
    # v0.7.1 新增:Agent 执行 Trace(每步 thought/decision/action/observation/duration/status)
    agent_trace = db.Column(db.JSON, nullable=True)
    # v0.7.1 新增:Trace 汇总统计(steps/总耗时/LLM耗时/Tool耗时/Tool调用统计)
    trace_summary = db.Column(db.JSON, nullable=True)
    iterations = db.Column(db.Integer, nullable=False, default=0)
    llm_error = db.Column(db.Text, nullable=True)
    # v0.7.1 新增:LLM 错误分类(timeout/rate_limit/server_error/network/auth/framework/json_parse/unknown)
    llm_error_type = db.Column(db.String(32), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'),
                             nullable=True, index=True)
    started_time = db.Column(db.DateTime, nullable=True)
    finished_time = db.Column(db.DateTime, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    contract = db.relationship(
        'Contract',
        backref=db.backref('reviews', lazy='dynamic')
    )
    analysis_task = db.relationship(
        'AnalysisTask',
        backref=db.backref('reviews', lazy='dynamic')
    )
    trigger_user = db.relationship(
        'User',
        backref=db.backref('triggered_reviews', lazy='dynamic')
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_risks=True, include_log=True,
                include_trace=True, include_contract=False):
        """
        转为 dict
        :param include_risks: 是否包含 risks 详情(列表场景可省略)
        :param include_log: 是否包含 tool_calls_log(列表场景可省略)
        :param include_trace: 是否包含 agent_trace / trace_summary(v0.7.1 新增)
        :param include_contract: 是否包含关联合同摘要(全局列表场景用)
        :return: dict
        """
        data = {
            'id': self.id,
            'review_no': self.review_no,
            'contract_id': self.contract_id,
            'task_id': self.task_id,
            'status': self.status,
            'risk_level': self.risk_level,
            'summary': self.summary,
            'risks': self.risks if include_risks else None,
            'tool_calls_log': self.tool_calls_log if include_log else None,
            'agent_trace': self.agent_trace if include_trace else None,
            'trace_summary': self.trace_summary if include_trace else None,
            'iterations': self.iterations,
            'llm_error': self.llm_error,
            'llm_error_type': self.llm_error_type,
            'error_message': self.error_message,
            'triggered_by': self.triggered_by,
            'started_time': self.started_time.strftime('%Y-%m-%d %H:%M:%S') if self.started_time else None,
            'finished_time': self.finished_time.strftime('%Y-%m-%d %H:%M:%S') if self.finished_time else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }
        if include_contract:
            c = self.contract
            data['contract'] = {
                'id': c.id,
                'title': c.title,
                'contract_no': c.contract_no,
            } if c else None
        return data

    def __repr__(self):
        return f'<ReviewReport {self.review_no} ({self.status}, risk={self.risk_level})>'
