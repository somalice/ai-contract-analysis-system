"""
招标需求模型(Sprint 7 - v0.9.1 增强)

对应 bid_requirements 表:
- id:主键
- requirement_no:需求编号(唯一,自动生成 BR-YYYYMMDDHHMMSS-XXXXXXXX)
- bid_document_id:外键 → bid_documents.id(1:1,重新解析时 UPDATE 原行)
- status:需求生命周期状态(draft / reviewing / approved / failed, v0.9.1 新增)
- version:需求版本号(默认 v1.0,重新解析自增,为后续 Diff 留扩展,v0.9.1 新增)
- requirement_data:15 字段 Requirement JSON
- field_sources:每个字段来源追踪(page_number/chunk_id/confidence/source_text, v0.9.1 新增)
- project_name/budget/deadline:冗余字段(列表展示用)
- field_count/missing_count/confidence:质量指标
- error_message:解析失败原因
- created_time / updated_time:时间戳

15 个 Requirement 字段(requirement_data JSON):
- project_name(项目名称) / tender_org(招标单位) / project_location / budget
- deadline / duration / delivery_requirements / technical_requirements[]
- qualification_requirements[] / scoring_criteria[] / bid_opening_time
- bid_validity / payment_terms / contact / other

status 状态机(v0.9.1 新增 draft/reviewing/approved 三态):
  draft → reviewing → approved
                  └→ draft(驳回重审)
  failed(解析失败,不进入审核流)

Proposal Agent 默认只读取 status='approved' 的需求。
"""
from datetime import datetime
from app.extensions.db import db


class BidRequirement(db.Model):
    """招标需求表(15 字段 Requirement,1:1 关联 BidDocument)"""
    __tablename__ = 'bid_requirements'

    # ---------- 需求生命周期状态(v0.9.1 扩展,向后兼容旧 status) ----------
    # draft:已解析完成,草稿态,未提交审核(Bid Agent 不读)
    # reviewing:审核中(Bid Agent 不读)
    # approved:审核通过(Bid Agent 默认只读此状态)
    # pending:瞬时态(已建记录未解析,正常立即转 failed/approved)
    # failed:解析失败(不进入审核流)
    VALID_STATUSES = ('draft', 'reviewing', 'approved', 'pending', 'failed')

    # Bid Agent 可读取的白名单
    AGENT_READABLE_STATUSES = ('approved',)
    # Requirement Review 审核机(单向推进,驳回可回 draft)
    REVIEW_TRANSITIONS = {
        'draft': ('reviewing',),
        'reviewing': ('approved', 'draft'),
        'approved': (),
        'pending': ('draft',),
        'failed': (),
    }

    # ---------- 15 字段清单(供校验与缺失统计) ----------
    REQUIRED_FIELDS = (
        'project_name', 'tender_org', 'project_location', 'budget', 'deadline',
        'duration', 'delivery_requirements', 'technical_requirements',
        'qualification_requirements', 'scoring_criteria', 'bid_opening_time',
        'bid_validity', 'payment_terms', 'contact', 'other',
    )

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    requirement_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    bid_document_id = db.Column(db.Integer, db.ForeignKey('bid_documents.id'),
                                nullable=False, unique=True, index=True)
    # ----- v0.9.1 增强:status 升级为生命周期 -----
    status = db.Column(db.String(32), nullable=False, default='draft')
    # ----- v0.9.1 新增:version 版本号 -----
    # 默认 v1.0,重新解析(重跑 Pipeline)时自增:v1.0 → v1.1 → v1.2
    version = db.Column(db.String(32), nullable=False, default='v1.0')
    requirement_data = db.Column(db.JSON, nullable=True)
    # ----- v0.9.1 新增:字段级来源追踪 -----
    # 结构: {field_name: {page_number, chunk_id, confidence, source_text}, ...}
    field_sources = db.Column(db.JSON, nullable=True)
    # 冗余字段(列表展示用,从 requirement_data 抽取)
    project_name = db.Column(db.String(255), nullable=True)
    budget = db.Column(db.String(64), nullable=True)
    deadline = db.Column(db.String(64), nullable=True)
    # 质量指标
    field_count = db.Column(db.Integer, nullable=False, default=0)
    missing_count = db.Column(db.Integer, nullable=False, default=15)
    confidence = db.Column(db.Float, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 版本号自增(重新解析时调用) ----------
    @staticmethod
    def next_version(current: str = None) -> str:
        """
        生成下一个版本号
        - None / 非法值 → v1.0
        - v1.0 → v1.1 / v1.9 → v1.10 / v2.5 → v2.6
        """
        if not current or not str(current).startswith('v'):
            return 'v1.0'
        try:
            ver_str = str(current)[1:]  # 去掉 'v'
            if '.' in ver_str:
                major, minor = ver_str.split('.', 1)
                return f'v{major}.{int(minor) + 1}'
            else:
                return f'v{int(ver_str) + 1}.0'
        except (ValueError, TypeError):
            return 'v1.0'

    # ---------- 序列化 ----------
    def to_dict(self, include_data=True, include_sources=True):
        """
        转为 dict
        :param include_data: 是否返回 requirement_data 详情
        :param include_sources: 是否返回 field_sources(字段来源追踪)
        :return: dict
        """
        return {
            'id': self.id,
            'requirement_no': self.requirement_no,
            'bid_document_id': self.bid_document_id,
            'status': self.status,
            'version': self.version,
            'requirement_data': self.requirement_data if include_data else None,
            'field_sources': self.field_sources if include_sources else None,
            # 冗余字段(列表展示用)
            'project_name': self.project_name,
            'budget': self.budget,
            'deadline': self.deadline,
            # 质量指标
            'field_count': self.field_count,
            'missing_count': self.missing_count,
            'confidence': self.confidence,
            'error_message': self.error_message,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return (
            f'<BidRequirement {self.requirement_no} '
            f'({self.status}@{self.version}, fields={self.field_count}/15)>'
        )
