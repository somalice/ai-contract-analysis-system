"""
操作审计日志模型(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

对应表 operation_logs:记录用户关键业务操作(登录 / 合同上传/审核/生成 / 知识库上传/删除 / 投标上传/解析/生成 等)。

设计原则(遵循 user_rules §15 日志规范):
- 必须包含:用户 / 请求 / 操作 / 时间戳 / 耗时 / 结果
- detail 仅记录摘要(文件名/模板 ID/文档标题等),**绝不存储明文密码、完整请求体、敏感字段**
- 全部字段(除 id/created_time/operation_type)可 null:审计失败绝不阻断业务

约束:
- 不删除旧日志:无 delete 接口(admin 仅查询,长期保留)
- to_dict() 含用户信息快照(username),用户删除后仍可追溯
"""
from datetime import datetime
from app.extensions.db import db


VALID_OPERATION_TYPES = (
    'user_login',
    'contract_upload', 'contract_analysis', 'contract_review',
    'contract_generate_preview', 'contract_generate',
    'knowledge_upload', 'knowledge_delete', 'knowledge_search',
    'bid_upload', 'bid_parse', 'bid_requirement_submit', 'bid_requirement_review', 'bid_generate',
    'template_upload', 'template_delete',
    'prompt_create', 'prompt_update', 'prompt_activate', 'prompt_delete',
    'evaluation_generate',
)


class OperationLog(db.Model):
    """操作审计日志"""
    __tablename__ = 'operation_logs'

    # ---------- 主键 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ---------- 用户(冗余 username 用于用户删除后仍可追溯)----------
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    username = db.Column(db.String(64), nullable=True)

    # ---------- 操作核心 ----------
    operation_type = db.Column(db.String(48), nullable=False, index=True)
    target_type = db.Column(db.String(32), nullable=True)   # contract / review / generation / proposal / knowledge / bid / template / prompt
    target_id = db.Column(db.Integer, nullable=True, index=True)

    # ---------- HTTP 维度 ----------
    method = db.Column(db.String(8), nullable=True)
    path = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(16), nullable=True, index=True)  # success / failed
    status_code = db.Column(db.Integer, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)

    # ---------- 内容摘要 ----------
    detail = db.Column(db.JSON, nullable=True)    # {'file_name':'...','title':'...','template_id':...} 等非敏感摘要
    error_message = db.Column(db.Text, nullable=True)

    # ---------- 时间戳 ----------
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # ---------- 关系 ----------
    user = db.relationship('User', lazy='joined')

    # ---------- 序列化 ----------
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username or (self.user.username if self.user else None),
            'operation_type': self.operation_type,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'method': self.method,
            'path': self.path,
            'status': self.status,
            'status_code': self.status_code,
            'duration_ms': self.duration_ms,
            'ip_address': self.ip_address,
            'detail': self.detail,
            'error_message': self.error_message,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }

    def __repr__(self):
        return f'<OperationLog id={self.id} op={self.operation_type} status={self.status}>'
