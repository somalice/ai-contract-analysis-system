"""
知识 Chunk 模型(Sprint 4 - v0.6.0)

对应 knowledge_chunks 表:
- id:主键
- document_id:外键 → knowledge_documents.id
- chunk_index:文档内 chunk 序号(从 0 开始)
- page_number:来源页码(PDF;docx/txt 为 0)
- start_offset:在全文中的起始字符偏移
- end_offset:在全文中的结束字符偏移
- token_count:Token 估算数(中文按字符数/1.5 近似)
- text:Chunk 文本内容
- metadata:扩展元信息(JSON,段落序号 / overlap 标记等)
- vector_id:FAISS 中的向量索引 ID(删除时定位)
- created_time:时间戳

关系:
- KnowledgeDocument → KnowledgeChunk 一对多

设计说明:
- 解决 Sprint 3 Final Check 三个问题:
  1. Chunk 缺少 Metadata → 本表含 page_number / start_offset / end_offset /
     token_count / metadata 全字段
  2. Chunk 未持久化 → 每个 chunk 落库一行,可重复检索
  3. Chunk 无 Overlap → chunker 切分时引入 overlap,start_offset/end_offset 记录
     真实位置(含 overlap 内容),相邻 chunk 在 offset 上有重叠区间
- vector_id:FAISS 向量 ID,删除 chunk 时据此从索引移除(FAISS remove_ids)
- 与 Sprint 3 的合同 Pipeline chunk 完全独立(合同 chunk 为内存 transient 产物)

约束:
- (document_id, chunk_index) 唯一约束:防同文档同序号重复
- 禁止修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
"""
from datetime import datetime
from app.extensions.db import db


class KnowledgeChunk(db.Model):
    """知识 Chunk 表(RAG 检索的最小单元,持久化)"""
    __tablename__ = 'knowledge_chunks'

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey('knowledge_documents.id'),
                            nullable=False, index=True)
    chunk_index = db.Column(db.Integer, nullable=False)
    page_number = db.Column(db.Integer, nullable=False, default=0)
    start_offset = db.Column(db.Integer, nullable=False, default=0)
    end_offset = db.Column(db.Integer, nullable=False, default=0)
    token_count = db.Column(db.Integer, nullable=False, default=0)
    text = db.Column(db.Text, nullable=False)
    # 注:'metadata' 是 SQLAlchemy Declarative 保留属性名,故 Python 属性用 chunk_metadata,
    # 通过 Column 第一参数映射 DB 列名为 metadata(满足任务书对 knowledge_chunks.metadata 字段要求)
    chunk_metadata = db.Column('metadata', db.JSON, nullable=True)
    vector_id = db.Column(db.Integer, nullable=True, index=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ---------- 唯一约束 ----------
    # 同一文档下同一 chunk_index 唯一(防止重复写入)
    __table_args__ = (
        db.UniqueConstraint('document_id', 'chunk_index',
                            name='uq_knowledge_chunk_doc_index'),
    )

    # ---------- 序列化 ----------
    def to_dict(self, preview=False):
        """
        转为 dict
        :param preview: 预览模式(文本截断到 200 字符,用于列表/概要)
        :return: dict
        """
        text = self.text or ''
        if preview and len(text) > 200:
            text = text[:200] + '...'
        return {
            'id': self.id,
            'document_id': self.document_id,
            'chunk_index': self.chunk_index,
            'page_number': self.page_number,
            'start_offset': self.start_offset,
            'end_offset': self.end_offset,
            'token_count': self.token_count,
            'text': text if preview else self.text,
            'metadata': self.chunk_metadata,
            'vector_id': self.vector_id,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }

    def __repr__(self):
        return f'<KnowledgeChunk doc={self.document_id} idx={self.chunk_index} (vec={self.vector_id})>'
