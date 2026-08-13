"""
合同生成记录模型(Sprint 6 - v0.8.0)

对应 generated_contracts 表:
- id:主键
- generation_no:生成编号(唯一,自动生成 GC-YYYYMMDDHHMMSS-XXXXXXXX)
- template_id:外键 → contract_templates.id(使用的模板)
- contract_id:外键 → contracts.id(生成的合同记录,生成成功后填,null=失败/预览)
- status:任务状态(pending / running / success / failed)
- input_variables:用户填写的变量键值(JSON)
- generated_clauses:AI 补充条款(JSON,结构见 SPRINT6_ANALYSIS §4.2)
- rag_references:RAG 命中规范(JSON,复用 Sprint 4 references 结构)
- validation_results:规则校验结果(JSON,{passed, issues})
- file_path:生成 .docx 路径(失败为 null)
- file_name:生成 .docx 文件名
- file_size:文件大小
- agent_trace:Agent 执行 Trace(JSON,复用 Sprint 5 结构)
- trace_summary:Trace 汇总(JSON)
- iterations:Agent 迭代次数
- llm_error:LLM 失败原因(成功为 null)
- llm_error_type:LLM 错误分类(复用 Sprint 5 枚举)
- error_message:整体失败原因(成功为 null)
- triggered_by:触发者外键 → users.id
- started_time / finished_time:执行时间
- created_time / updated_time:时间戳

关系:
- ContractTemplate → GeneratedContract 一对多(通过 backref,不修改 contract_template.py)
- Contract → GeneratedContract 一对多(通过 backref,不修改 contract.py)
- User → GeneratedContract 一对多(通过 backref,不修改 user.py)

状态机(单向推进,与 ReviewReport 一致):
pending → running → success
                   └→ failed

设计说明:
- 任务化:每次生成独立可追踪,支持重试(创建新 GeneratedContract)
- 同步执行:Sprint 6 不引入 Celery,Agent 在 HTTP 请求内同步完成
- 不修改 Sprint 3/4/5 任何表
"""
from datetime import datetime
from app.extensions.db import db


class GeneratedContract(db.Model):
    """合同生成记录表(Contract Generation Agent 执行实例)"""
    __tablename__ = 'generated_contracts'

    # ---------- 任务状态枚举 ----------
    VALID_STATUSES = ('pending', 'running', 'success', 'failed')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    generation_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('contract_templates.id'),
                            nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    input_variables = db.Column(db.JSON, nullable=True)
    generated_clauses = db.Column(db.JSON, nullable=True)
    rag_references = db.Column(db.JSON, nullable=True)
    validation_results = db.Column(db.JSON, nullable=True)
    file_path = db.Column(db.String(512), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    agent_trace = db.Column(db.JSON, nullable=True)
    trace_summary = db.Column(db.JSON, nullable=True)
    iterations = db.Column(db.Integer, nullable=False, default=0)
    llm_error = db.Column(db.Text, nullable=True)
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
    template = db.relationship(
        'ContractTemplate',
        backref=db.backref('generations', lazy='dynamic')
    )
    contract = db.relationship(
        'Contract',
        backref=db.backref('generations', lazy='dynamic')
    )
    trigger_user = db.relationship(
        'User',
        backref=db.backref('triggered_generations', lazy='dynamic')
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_clauses=True, include_trace=True,
                include_contract=False, include_template=True):
        """
        转为 dict
        :param include_clauses: 是否包含 generated_clauses / rag_references / validation_results(列表场景可省略)
        :param include_trace: 是否包含 agent_trace / trace_summary
        :param include_contract: 是否包含关联合同摘要(生成成功时用)
        :param include_template: 是否包含关联模板摘要
        :return: dict(不含 file_path 内部路径)
        """
        data = {
            'id': self.id,
            'generation_no': self.generation_no,
            'template_id': self.template_id,
            'contract_id': self.contract_id,
            'status': self.status,
            'input_variables': self.input_variables,
            'generated_clauses': self.generated_clauses if include_clauses else None,
            'rag_references': self.rag_references if include_clauses else None,
            'validation_results': self.validation_results if include_clauses else None,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
            } if self.file_name else None,
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
        if include_template:
            t = self.template
            data['template'] = {
                'id': t.id,
                'name': t.name,
                'template_no': t.template_no,
                'contract_type': t.contract_type,
            } if t else None
        if include_contract:
            c = self.contract
            data['contract'] = {
                'id': c.id,
                'contract_no': c.contract_no,
                'title': c.title,
                'status': c.status,
            } if c else None
        return data

    def __repr__(self):
        return f'<GeneratedContract {self.generation_no} ({self.status})>'
