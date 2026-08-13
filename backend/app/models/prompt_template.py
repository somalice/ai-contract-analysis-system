"""
Prompt 模板管理模型(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

对应表 prompt_templates:
- 存储 3 个 Agent + RAG 的 System/Human Prompt,支持在线版本切换(无需重启服务)
- 同一 name 只能有一个 active(Service 层保证;数据库层增加 UNIQUE(name, status_active_flag) 成本高,用 Service 事务保证)

覆盖 5 种 name:
- contract_review     Sprint 5 Review Agent
- contract_generation Sprint 6 Generation Agent
- bid_proposal        Sprint 7 Proposal Agent
- bid_requirement     Sprint 7 Bid Requirement Extractor
- rag_answer          Sprint 4 RAG Answer Prompt

设计原则(遵循 user_rules §11 Prompt 管理):
- content 字段拆分为 system_prompt + human_prompt(与现有 prompts/*.md 的 ## Section 解析完全对齐)
- 版本号 version 语义:v1 / v1.1 / v2,同一 name 可并存多个 version,但仅一个 active
- status: active / inactive / draft
"""
from datetime import datetime
from app.extensions.db import db


VALID_STATUS = ('active', 'inactive', 'draft')
VALID_NAMES = (
    'contract_review',
    'contract_generation',
    'bid_proposal',
    'bid_requirement',
    'rag_answer',
    'contract_extract',
)


class PromptTemplate(db.Model):
    """Prompt 模板"""
    __tablename__ = 'prompt_templates'

    # ---------- 主键 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ---------- 标识 ----------
    name = db.Column(db.String(64), nullable=False, index=True)      # VALID_NAMES
    version = db.Column(db.String(32), nullable=False, default='v1')
    status = db.Column(db.String(16), nullable=False, default='draft', index=True)  # VALID_STATUS

    # ---------- 内容(拆分为 System / Human,与 .md ## 解析 1:1 对齐)----------
    system_prompt = db.Column(db.Text, nullable=False)
    human_prompt = db.Column(db.Text, nullable=False)

    # ---------- 元信息 ----------
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    # ---------- 时间戳 ----------
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    creator = db.relationship('User', lazy='joined')

    # ---------- 序列化 ----------
    def to_dict(self, include_content=True):
        d = {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'status': self.status,
            'description': self.description,
            'created_by': self.created_by,
            'created_by_username': self.creator.username if self.creator else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }
        if include_content:
            d['system_prompt'] = self.system_prompt
            d['human_prompt'] = self.human_prompt
        return d

    def __repr__(self):
        return f'<PromptTemplate id={self.id} name={self.name} version={self.version} status={self.status}>'
