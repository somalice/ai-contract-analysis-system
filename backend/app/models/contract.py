"""
合同模型(Sprint 2 - v0.4.0)

对应 contracts 表:
- id:主键
- contract_no:合同编号(唯一,自动生成)
- title:合同标题(默认取文件名去扩展名)
- contract_type:合同类型(默认"未分类")
- description:描述(可选)
- creator_id:创建者外键 → users.id
- status:生命周期状态(draft / reviewed / archived)
- file_name:原始文件名
- file_path:服务器存储路径(UUID 文件名,不暴露给客户端)
- file_size:文件大小(字节)
- analysis_status:AI 分析状态(processing / completed / failed)
- analysis_result:AI 提取的字段(JSON)
- created_time / updated_time:时间戳

关系:
- User → Contract 一对多(通过 backref,不修改 user.py)

约束:
- contract_no 唯一
- status 仅允许三个枚举值(draft/reviewed/archived)
- 状态机:仅允许 draft→reviewed→archived 单向流转
- to_dict() 不返回 file_path(内部路径)
"""
import os
from datetime import datetime, timedelta
from app.extensions.db import db


class Contract(db.Model):
    """合同表"""
    __tablename__ = 'contracts'

    # ---------- 状态枚举 ----------
    # 生命周期状态:Sprint 2 仅实现 draft / reviewed / archived
    # (uploaded / analyzing / approved 为后续 Sprint 预留,不在本阶段实现)
    VALID_STATUSES = ('draft', 'reviewed', 'archived')

    # AI 分析状态(独立维度,无状态机)
    VALID_ANALYSIS_STATUSES = ('pending', 'processing', 'completed', 'failed')

    # 状态机转换矩阵:current → {允许的 target}
    STATUS_TRANSITIONS = {
        'draft': {'reviewed'},
        'reviewed': {'archived'},
        'archived': set(),  # 终态,不可转出
    }

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    contract_type = db.Column(db.String(64), nullable=False, default='未分类')
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='draft')
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    analysis_status = db.Column(db.String(32), nullable=False, default='processing')
    analysis_result = db.Column(db.JSON, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    # 通过 backref 在 User 上添加 contracts 关系(无需修改 user.py)
    # lazy='dynamic' 返回查询对象,避免一次性加载所有合同
    creator = db.relationship(
        'User',
        backref=db.backref('contracts', lazy='dynamic')
    )

    # ---------- 状态机校验 ----------
    @classmethod
    def is_valid_transition(cls, current_status, target_status):
        """
        校验状态转换是否合法
        :param current_status: 当前状态
        :param target_status: 目标状态
        :return: bool
        """
        if current_status not in cls.VALID_STATUSES:
            return False
        if target_status not in cls.VALID_STATUSES:
            return False
        return target_status in cls.STATUS_TRANSITIONS.get(current_status, set())

    # ---------- 序列化 ----------
    def to_dict(self, include_analysis=True):
        """
        转为 dict
        :param include_analysis: 是否包含 analysis_result(列表场景可省略)
        :return: dict(不含 file_path 内部路径)

        注意:file_path 为服务器内部存储路径,不暴露给客户端;
             客户端仅需 file_info(name + size)。
        """
        return {
            'id': self.id,
            'contract_no': self.contract_no,
            'title': self.title,
            'contract_type': self.contract_type,
            'description': self.description,
            'status': self.status,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
            },
            'analysis_status': self.analysis_status,
            'analysis_result': self.analysis_result if include_analysis else None,
            'creator': self.creator.to_dict() if self.creator else None,
            'creator_id': self.creator_id,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return f'<Contract {self.contract_no} ({self.status})>'
