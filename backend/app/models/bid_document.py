"""
招标文档模型(Sprint 7 - v0.9.0)

对应 bid_documents 表:
- id:主键
- bid_no:招标编号(唯一,自动生成 BD-YYYYMMDDHHMMSS-XXXXXXXX)
- title:招标标题(默认取文件名去扩展名)
- file_name:原始文件名(展示用)
- file_path:服务器存储路径(UUID 文件名,不暴露给客户端)
- file_size:文件大小(字节)
- file_type:文件类型(pdf / image)
- page_count:页数(PDF,图片默认 1)
- text_content:提取的全文(extract / ocr 产物,详情按需返回)
- text_length:文本长度
- parse_status:需求解析状态(pending / processing / success / failed)
- extract_method:文本提取方法(pdfplumber / deepseek_ocr / none)
- error_message:解析失败原因
- uploader_id:上传者外键 → users.id
- created_time / updated_time:时间戳

关系:
- User → BidDocument 一对多(通过 backref,不修改 user.py)
- BidDocument → BidRequirement 一对一(uselist=False,重新解析时 UPDATE 原行)
- BidDocument → GeneratedProposal 一对多

设计说明:
- 独立表,不挂 contracts(招标 ≠ 合同,保持 Sprint 2 合同表纯净)
- text_content 落库后,LLM 失败重跑无需重新 OCR/提取(节省算力)
- parse_status 状态机:pending → processing → success / failed(单向推进,与 AnalysisTask 一致)
- to_dict() 不返回 file_path(内部路径);text_content 默认不返回(按需 include_text=True)

约束:
- 不修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
- 不修改 Sprint 6 的 contract_templates / generated_contracts 表
"""
from datetime import datetime
from app.extensions.db import db


class BidDocument(db.Model):
    """招标文档表(招标文件 + 提取文本,独立于合同 documents)"""
    __tablename__ = 'bid_documents'

    # ---------- 文件类型枚举 ----------
    VALID_FILE_TYPES = ('pdf', 'image')

    # ---------- 解析状态枚举 ----------
    # pending:已建记录未解析
    # processing:正在解析(同步执行,瞬时)
    # success:解析完成,已生成 BidRequirement
    # failed:解析失败(LLM 不可用 / 文本为空等)
    VALID_PARSE_STATUSES = ('pending', 'processing', 'success', 'failed')

    # ---------- 提取方法枚举 ----------
    VALID_EXTRACT_METHODS = ('pdfplumber', 'deepseek_ocr', 'none')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bid_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    file_type = db.Column(db.String(16), nullable=False, default='pdf')
    page_count = db.Column(db.Integer, nullable=False, default=0)
    text_content = db.Column(db.Text, nullable=True)
    text_length = db.Column(db.Integer, nullable=False, default=0)
    parse_status = db.Column(db.String(32), nullable=False, default='pending')
    extract_method = db.Column(db.String(32), nullable=False, default='none')
    error_message = db.Column(db.Text, nullable=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                            nullable=False, index=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    uploader = db.relationship(
        'User',
        backref=db.backref('bid_documents', lazy='dynamic')
    )
    # 1:1:一个招标文件对应一个 Requirement(重新解析 UPDATE 原行,不 append)
    requirement = db.relationship(
        'BidRequirement',
        backref='bid_document',
        uselist=False,
        cascade='all, delete-orphan'
    )
    # 1:N:一个招标文件可被多次生成投标方案
    proposals = db.relationship(
        'GeneratedProposal',
        backref='bid_document',
        lazy='dynamic'
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_text=False, include_requirement=False):
        """
        转为 dict
        :param include_text: 是否返回 text_content(详情场景可传 True,列表场景 False)
        :param include_requirement: 是否返回关联的 Requirement 概要
        :return: dict(不含 file_path 内部路径)

        注意:file_path 为服务器内部存储路径,不暴露给客户端;
             text_content 可能很大,默认不返回,按需开启。
        """
        data = {
            'id': self.id,
            'bid_no': self.bid_no,
            'title': self.title,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
                'type': self.file_type,
            },
            'page_count': self.page_count,
            'text_length': self.text_length,
            'parse_status': self.parse_status,
            'extract_method': self.extract_method,
            'error_message': self.error_message,
            'uploader': self.uploader.to_dict() if self.uploader else None,
            'uploader_id': self.uploader_id,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }
        if include_text:
            data['text_content'] = self.text_content
        if include_requirement:
            r = self.requirement
            data['requirement'] = r.to_dict() if r else None
        return data

    def __repr__(self):
        return f'<BidDocument {self.bid_no} ({self.parse_status})>'
