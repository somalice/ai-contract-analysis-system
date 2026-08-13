"""
合同模板模型(Sprint 6 - v0.8.0)

对应 contract_templates 表:
- id:主键
- template_no:模板编号(唯一,自动生成 TPL-YYYYMMDDHHMMSS-XXXXXXXX)
- name:模板名称
- description:模板说明(可选)
- contract_type:合同类型(采购/销售/服务/未分类 等)
- file_name:原始文件名
- file_path:服务器存储路径(UUID 文件名,不暴露给客户端)
- file_size:文件大小(字节)
- variables:解析出的变量列表(JSON,结构见 SPRINT6_ANALYSIS §2.2)
- variable_count:变量数量(冗余,便于列表展示)
- version:模板版本(语义化版本字符串,默认 v1.0;同名模板可通过 version 区分不同版本)
- status:状态(active / disabled,可反复切换)
- creator_id:创建者外键 → users.id
- created_time / updated_time:时间戳

关系:
- User → ContractTemplate 一对多(通过 backref,不修改 user.py)
- ContractTemplate → GeneratedContract 一对多(通过 backref)

状态:
- active:可使用(出现在"可生成"列表)
- disabled:停用(不出现在"可生成"列表,但历史生成记录仍可查)
- active ⇄ disabled 可反复切换(无单向约束,与合同状态机不同)

约束:
- template_no 唯一
- to_dict() 不返回 file_path(内部路径)
- 不修改 Sprint 0~5 任何模型
"""
from datetime import datetime
from app.extensions.db import db


class ContractTemplate(db.Model):
    """合同模板表"""
    __tablename__ = 'contract_templates'

    # ---------- 状态枚举 ----------
    VALID_STATUSES = ('active', 'disabled')

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    contract_type = db.Column(db.String(64), nullable=False, default='未分类')
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    # variables: [{name, label, required, sample}]
    variables = db.Column(db.JSON, nullable=True)
    variable_count = db.Column(db.Integer, nullable=False, default=0)
    # version:模板版本(语义化版本,默认 v1.0;同名模板可通过 version 区分迭代版本)
    version = db.Column(db.String(32), nullable=False, default='v1.0')
    status = db.Column(db.String(32), nullable=False, default='active')
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                           nullable=False, index=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    creator = db.relationship(
        'User',
        backref=db.backref('templates', lazy='dynamic')
    )

    # ---------- 序列化 ----------
    def to_dict(self, include_variables=True):
        """
        转为 dict
        :param include_variables: 是否包含 variables 详情(列表场景可省略)
        :return: dict(不含 file_path 内部路径)
        """
        return {
            'id': self.id,
            'template_no': self.template_no,
            'name': self.name,
            'description': self.description,
            'contract_type': self.contract_type,
            'file_info': {
                'name': self.file_name,
                'size': self.file_size,
            },
            'variables': self.variables if include_variables else None,
            'variable_count': self.variable_count,
            'version': self.version,
            'status': self.status,
            'creator': self.creator.to_dict() if self.creator else None,
            'creator_id': self.creator_id,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return f'<ContractTemplate {self.template_no} ({self.status})>'
