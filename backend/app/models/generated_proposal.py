"""
投标生成记录模型(Sprint 7 - v0.9.0)

对应 generated_proposals 表(镜像 generated_contracts):
- id:主键
- proposal_no:生成编号(唯一,自动生成 PR-YYYYMMDDHHMMSS-XXXXXXXX)
- bid_document_id:外键 → bid_documents.id(关联的招标文件)
- status:任务状态(pending / running / success / failed)
- input_data:输入参数 JSON(bid_id / company_profile_overrides / options)
- generated_sections:AI 生成的章节 JSON(冗余,与 proposal_sections 表互为镜像)
- rag_references:RAG 命中规范 JSON(复用 Sprint 4 references 结构)
- validation_results:规则校验结果 JSON({passed, issues})
- file_path:生成 .docx 路径(失败为 null)
- file_name:生成 .docx 文件名
- file_size:文件大小
- agent_trace:Agent 执行 Trace JSON(复用 Sprint 5 结构)
- trace_summary:Trace 汇总 JSON
- iterations:Agent 迭代次数
- llm_error:LLM 失败原因(成功为 null)
- llm_error_type:LLM 错误分类(复用 Sprint 5 枚举)
- error_message:整体失败原因(成功为 null)
- triggered_by:触发者外键 → users.id
- started_time / finished_time:执行时间
- created_time / updated_time:时间戳

关系:
- BidDocument → GeneratedProposal 一对多(通过 backref,不修改 bid_document.py)
- User → GeneratedProposal 一对多(通过 backref,不修改 user.py)
- GeneratedProposal → ProposalSection 一对多(cascade='all, delete-orphan')

状态机(单向推进,与 GeneratedContract 一致):
pending → running → success
                   └→ failed

设计说明:
- 镜像 generated_contracts 表结构(1:1 对齐),便于前端复用 GenerationDetail Timeline
- generated_sections JSON 与 proposal_sections 表互为镜像:
  - JSON 字段供快速预览(列表 / 详情接口直接返回)
  - proposal_sections 表供独立查询 / 排序 / 分页(cascade delete)
- 不修改 Sprint 6 的 generated_contracts 表

约束:
- 不修改 Sprint 3/4/5/6 任何表
"""
from datetime import datetime
from app.extensions.db import db


class GeneratedProposal(db.Model):
    """投标生成记录表(Proposal Agent 执行实例)"""
    __tablename__ = 'generated_proposals'

    # ---------- 任务状态枚举 ----------
    VALID_STATUSES = ('pending', 'running', 'success', 'failed')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proposal_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    bid_document_id = db.Column(db.Integer, db.ForeignKey('bid_documents.id'),
                                nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    input_data = db.Column(db.JSON, nullable=True)
    generated_sections = db.Column(db.JSON, nullable=True)
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
    trigger_user = db.relationship(
        'User',
        backref=db.backref('triggered_proposals', lazy='dynamic')
    )
    # 1:N:一个生成记录包含多个章节(technical / commercial / responsive / qualification / summary)
    sections = db.relationship(
        'ProposalSection',
        backref='proposal',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ProposalSection.sort_order'
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_sections=True, include_trace=True,
                include_bid=False):
        """
        转为 dict
        :param include_sections: 是否包含 generated_sections / rag_references / validation_results(列表场景可省略)
        :param include_trace: 是否包含 agent_trace / trace_summary
        :param include_bid: 是否包含关联招标文件摘要
        :return: dict(不含 file_path 内部路径)
        """
        data = {
            'id': self.id,
            'proposal_no': self.proposal_no,
            'bid_document_id': self.bid_document_id,
            'status': self.status,
            'input_data': self.input_data,
            'generated_sections': self.generated_sections if include_sections else None,
            'rag_references': self.rag_references if include_sections else None,
            'validation_results': self.validation_results if include_sections else None,
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
        if include_bid:
            b = self.bid_document
            data['bid'] = {
                'id': b.id,
                'bid_no': b.bid_no,
                'title': b.title,
                'parse_status': b.parse_status,
            } if b else None
        return data

    def __repr__(self):
        return f'<GeneratedProposal {self.proposal_no} ({self.status})>'
