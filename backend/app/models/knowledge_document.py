"""
知识文档模型(Sprint 4 - v0.6.0)

对应 knowledge_documents 表:
- id:主键
- doc_no:文档编号(唯一,自动生成 KD-YYYYMMDDHHMMSS-XXXXXXXX)
- title:文档标题
- knowledge_type:知识类型(Sprint 7 新增,general/contract/bid/company/case/qualification)
- source_type:来源类型(manual_upload / contract 等,本阶段仅 manual_upload)
- file_name:原始文件名(展示用)
- file_path:服务器存储路径(UUID 文件名,不暴露给客户端)
- file_size:文件大小(字节)
- file_type:文件类型(pdf / docx / txt)
- page_count:页数(PDF;docx/txt 默认 1)
- text_content:提取的全文(loader 产物,可空)
- text_length:文本长度
- chunk_count:Chunk 数量(冗余,列表展示用,避免 COUNT JOIN)
- embedding_status:Embedding 状态(pending / processing / completed / failed)
- vector_indexed:是否已写入 FAISS 索引
- uploader_id:上传者外键 → users.id
- status:文档状态(active / deleted,软删)
- error_message:处理失败原因
- created_time / updated_time:时间戳

关系:
- User → KnowledgeDocument 一对多(通过 backref,不修改 user.py)
- KnowledgeDocument → KnowledgeChunk 一对多

设计说明:
- 知识文档独立于合同 documents 表(Sprint 3),职责分离:
  合同 documents 服务于合同字段提取;知识文档服务于 RAG 检索
- embedding_status 状态机:pending → processing → completed / failed
  (本阶段同步执行,processing 仅瞬时;为 Sprint 8 异步化预留)
- 软删:删除时置 status=deleted 并从 FAISS 移除向量,物理文件保留以便审计
- to_dict() 不返回 file_path(内部路径)
- text_content 可能很大(Text),列表场景不返回

约束:
- 禁止修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
"""
from datetime import datetime
from app.extensions.db import db


class KnowledgeDocument(db.Model):
    """知识文档表(RAG 知识库的文档元信息)"""
    __tablename__ = 'knowledge_documents'

    # ---------- 文件类型枚举 ----------
    VALID_FILE_TYPES = ('pdf', 'docx', 'txt')

    # ---------- 来源类型枚举 ----------
    # manual_upload:用户手动上传;contract:未来从合同导入(Sprint 4 仅 manual_upload)
    VALID_SOURCE_TYPES = ('manual_upload', 'contract')

    # ---------- Embedding 状态枚举 ----------
    # pending:已建记录未处理
    # processing:正在切分 / Embedding / 入库(本阶段同步,瞬时)
    # completed:已写入 FAISS,可检索
    # failed:处理失败(模型不可用 / 文本为空等)
    VALID_EMBEDDING_STATUSES = ('pending', 'processing', 'completed', 'failed')

    # ---------- 文档状态枚举 ----------
    # active:可用;deleted:软删(从 FAISS 移除,记录保留)
    VALID_STATUSES = ('active', 'deleted')

    # ---------- 知识类型枚举(Sprint 7 - v0.9.0 新增) ----------
    # general:通用(默认,旧行自动回填)
    # contract:合同规范(Sprint 4 历史合同知识)
    # bid:招标规范(招标法规 / 评标办法)
    # company:企业资料(公司简介 / 资质 / 业绩,供 ProposalAgent 检索)
    # case:案例库(类似项目案例)
    # qualification:资质证书(ISO / 行业资质)
    VALID_KNOWLEDGE_TYPES = ('general', 'contract', 'bid', 'company',
                             'case', 'qualification')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    doc_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    # knowledge_type:知识类型(Sprint 7 - v0.9.0 新增,additive,默认 general)
    # 用于区分企业资料 / 招标规范 / 案例等,供 BidKnowledgeSearchTool 后过滤
    knowledge_type = db.Column(db.String(32), nullable=False, default='general', index=True)
    source_type = db.Column(db.String(32), nullable=False, default='manual_upload')
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    file_type = db.Column(db.String(16), nullable=False, default='txt')
    page_count = db.Column(db.Integer, nullable=False, default=0)
    text_content = db.Column(db.Text, nullable=True)
    text_length = db.Column(db.Integer, nullable=False, default=0)
    chunk_count = db.Column(db.Integer, nullable=False, default=0)
    embedding_status = db.Column(db.String(32), nullable=False, default='pending')
    vector_indexed = db.Column(db.Boolean, nullable=False, default=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='active')
    error_message = db.Column(db.Text, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    # User → KnowledgeDocument 一对多(通过 backref,不修改 user.py)
    uploader = db.relationship(
        'User',
        backref=db.backref('knowledge_documents', lazy='dynamic')
    )
    # KnowledgeDocument → KnowledgeChunk 一对多
    chunks = db.relationship(
        'KnowledgeChunk',
        backref='document',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_text=False, include_chunks=False):
        """
        转为 dict
        :param include_text: 是否返回 text_content(详情场景可传 True,列表场景 False)
        :param include_chunks: 是否返回 chunks 概要(详情场景)
        :return: dict(不含 file_path 内部路径)

        注意:file_path 为服务器内部存储路径,不暴露给客户端;
             text_content 可能很大,默认不返回,按需开启。
        """
        data = {
            'id': self.id,
            'doc_no': self.doc_no,
            'title': self.title,
            'knowledge_type': self.knowledge_type,
            'source_type': self.source_type,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
                'type': self.file_type,
            },
            'page_count': self.page_count,
            'text_length': self.text_length,
            'chunk_count': self.chunk_count,
            'embedding_status': self.embedding_status,
            'vector_indexed': self.vector_indexed,
            'uploader': self.uploader.to_dict() if self.uploader else None,
            'uploader_id': self.uploader_id,
            'status': self.status,
            'error_message': self.error_message,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }
        if include_text:
            data['text_content'] = self.text_content
        if include_chunks:
            # 仅返回概要(前 3 个 chunk 的预览),避免详情接口返回过多数据
            chunk_rows = self.chunks.order_by('chunk_index').limit(3).all()
            data['chunks_preview'] = [c.to_dict(preview=True) for c in chunk_rows]
        return data

    def __repr__(self):
        return f'<KnowledgeDocument {self.doc_no} ({self.embedding_status})>'
