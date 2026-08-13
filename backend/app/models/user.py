"""
用户模型(Sprint 1 - v0.3.0)

对应 users 表:
- id:主键
- username:用户名(唯一,索引)
- password_hash:密码哈希(Werkzeug,禁止保存明文)
- role:角色(admin / contract_manager / employee)
- created_time / updated_time:时间戳

约束:
- username 唯一(数据库层 unique + 应用层校验)
- role 仅允许三个枚举值
- 密码仅以 hash 形式存储
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions.db import db


class User(db.Model):
    """用户表"""
    __tablename__ = 'users'

    # 角色枚举(仅这三个,禁止扩展复杂 RBAC)
    VALID_ROLES = ('admin', 'contract_manager', 'employee')

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='employee')
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    # ---------- 密码管理 ----------
    def set_password(self, password):
        """设置密码(仅保存 hash)"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """校验密码"""
        return check_password_hash(self.password_hash, password)

    # ---------- 序列化 ----------
    def to_dict(self):
        """转为 dict(不含 password_hash)"""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
            'updated_time': self.updated_time.strftime('%Y-%m-%d %H:%M:%S') if self.updated_time else None,
        }

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
