"""
文档模型(Sprint 3 - v0.5.0)

对应 documents 表:
- id:主键
- contract_id:外键 → contracts.id(一个合同对应一个文档,本阶段 1:1)
- file_name:原始文件名(展示用)
- file_path:服务器存储路径(UUID 文件名,不暴露给客户端)
- file_size:文件大小(字节)
- file_type:文件类型(pdf / image)
- page_count:页数(PDF,图片默认 1)
- text_content:提取的全文(extract / ocr Stage 产物)
- text_length:文本长度(text_content 的 len)
- extract_method:文本提取方法(pdfplumber / deepseek_ocr / none)
- created_time / updated_time:时间戳

关系:
- Contract → Document 一对多(通过 backref,不修改 contract.py)
- Document → AnalysisTask 一对多(一个文档可被多次分析,支持重跑)

设计说明:
- 将"文件 + 提取文本"从 contracts 表解耦,contracts 只保留合同业务元信息
- text_content 落库后,LLM 失败重跑无需重新 OCR(节省算力)
- 本阶段 contract_id 不建唯一约束(允许未来多版本),但业务层保证 1:1

约束:
- to_dict() 不返回 file_path(内部路径)
- text_content 可能很大(Text 类型),列表场景不返回
"""
from datetime import datetime
from app.extensions.db import db


class Document(db.Model):
    """文档表(合同文件 + 提取文本)"""
    __tablename__ = 'documents'

    # ---------- 文件类型枚举 ----------
    VALID_FILE_TYPES = ('pdf', 'image')

    # ---------- 提取方法枚举 ----------
    # pdfplumber:文本型 PDF 提取
    # deepseek_ocr:图片 OCR(DeepSeek Vision)
    # none:未提取 / 提取失败
    VALID_EXTRACT_METHODS = ('pdfplumber', 'deepseek_ocr', 'none')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    file_type = db.Column(db.String(16), nullable=False, default='pdf')
    page_count = db.Column(db.Integer, nullable=False, default=0)
    text_content = db.Column(db.Text, nullable=True)
    text_length = db.Column(db.Integer, nullable=False, default=0)
    extract_method = db.Column(db.String(32), nullable=False, default='none')
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    # Contract → Document 一对多(通过 backref,不修改 contract.py)
    contract = db.relationship(
        'Contract',
        backref=db.backref('documents', lazy='dynamic')
    )
    # Document → AnalysisTask 一对多(一个文档可被多次分析)
    tasks = db.relationship(
        'AnalysisTask',
        backref='document',
        lazy='dynamic'
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_text=False):
        """
        转为 dict
        :param include_text: 是否返回 text_content(详情场景可传 True,列表场景 False)
        :return: dict(不含 file_path 内部路径)

        注意:file_path 为服务器内部存储路径,不暴露给客户端;
             text_content 可能很大,默认不返回,按需开启。
        """
        return {
            'id': self.id,
            'contract_id': self.contract_id,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
                'type': self.file_type,
            },
            'page_count': self.page_count,
            'text_length': self.text_length,
            'extract_method': self.extract_method,
            'text_content': self.text_content if include_text else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return f'<Document {self.id} (contract={self.contract_id}, {self.file_type})>'
