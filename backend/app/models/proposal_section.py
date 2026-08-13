"""
投标章节模型(Sprint 7 - v0.9.1 增强)

对应 proposal_sections 表:
- id:主键
- proposal_id:外键 → generated_proposals.id(1:N 关系)
- section_type/section_name/content/source/sort_order/created_time(同上)
- references:RAG 引用 JSON(复用 Sprint 4 结构,已含 document_id/chunk_id/page_number/score)
- similarity_score:章节 TOP 引用的相似度(冗余,便于列表过滤,v0.9.1 新增)
- document_id:章节 TOP 引用的知识文档 ID(冗余,便于 join 查询,v0.9.1 新增)

Sprint 7.1 Bid References 要求:document_id / chunk_id / page_number / similarity_score
已在 references JSON 中完整存在,本层仅新增 2 个冗余列便于上层独立查询。
"""
from datetime import datetime
from app.extensions.db import db


class ProposalSection(db.Model):
    """投标章节表(投标文件的章节级内容)"""
    __tablename__ = 'proposal_sections'

    # ---------- 章节类型枚举 ----------
    VALID_SECTION_TYPES = ('technical', 'commercial', 'responsive',
                           'qualification', 'summary')
    REQUIRED_SECTION_TYPES = ('technical', 'commercial', 'responsive', 'qualification')
    DEFAULT_SORT_ORDER = {
        'technical': 1, 'commercial': 2, 'responsive': 3,
        'qualification': 4, 'summary': 5,
    }
    VALID_SOURCES = ('ai', 'template', 'rule')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    proposal_id = db.Column(db.Integer, db.ForeignKey('generated_proposals.id'),
                           nullable=False, index=True)
    section_type = db.Column(db.String(32), nullable=False)
    section_name = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(32), nullable=False, default='ai')
    references = db.Column(db.JSON, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # v0.9.1 新增:统一引用格式的冗余列(便于 SQL 查询/过滤,不修改 references JSON)
    similarity_score = db.Column(db.Float, nullable=True)
    document_id = db.Column(db.Integer, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ---------- 序列化 ----------
    def to_dict(self, include_content=True, include_references=True):
        """转为 dict(返回 unified reference:document_id/chunk_id/page_number/similarity_score)"""
        refs = self.references if include_references else None
        # 从 references JSON 抽取 TOP 引用到顶层,保持与 Sprint 5 Contract Review 统一格式
        top_ref = (refs or [{}])[0] if refs else {}
        return {
            'id': self.id,
            'proposal_id': self.proposal_id,
            'section_type': self.section_type,
            'section_name': self.section_name,
            'content': self.content if include_content else None,
            'source': self.source,
            # 章节级统一引用格式(4 字段,顶层,便于前端统一展示)
            'top_reference': {
                'document_id': self.document_id or top_ref.get('document_id'),
                'chunk_id': top_ref.get('chunk_id'),
                'page_number': top_ref.get('page_number'),
                'similarity_score': (
                    float(self.similarity_score)
                    if self.similarity_score is not None else top_ref.get('score')
                ),
            },
            'references': refs,
            'sort_order': self.sort_order,
            'similarity_score': self.similarity_score,
            'document_id': self.document_id,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }

    def __repr__(self):
        return f'<ProposalSection {self.section_type} (proposal={self.proposal_id})>'
