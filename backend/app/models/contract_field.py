"""
合同字段模型(Sprint 3 - v0.5.0)

对应 contract_fields 表:
- id:主键
- contract_id:外键 → contracts.id
- task_id:外键 → analysis_tasks.id(来源任务,支持多版本追溯)
- field_name:字段名(8 个枚举之一)
- field_value:字段值(允许 null,表示未提取到)
- confidence:置信度 0.0–1.0(LLM 自评,缺失字段为 0.0)
- source_text:字段来源文本片段(可追溯,允许 null)
- created_time:时间戳

字段名枚举(8 个,与 LLM 输出契约一致):
- contract_no     合同编号
- contract_name   合同名称
- party_a         甲方
- party_b         乙方
- amount          合同金额
- sign_date       签署日期
- payment_method  付款方式
- valid_period    有效期

关系:
- Contract → ContractField 一对多
- AnalysisTask → ContractField 一对多

设计说明:
- 替代 Sprint 2 的 contracts.analysis_result JSON 列
- 字段级 confidence + source_text,支持审计与质量评估
- 每字段一行,可独立查询 / 索引
- (contract_id, field_name, task_id) 唯一约束:同任务同字段不重复

兼容策略:
- 详情接口优先读 contract_fields;若空则降级读 contracts.analysis_result(Sprint 2 旧合同)
"""
from datetime import datetime
from app.extensions.db import db


class ContractField(db.Model):
    """合同字段表(LLM 结构化提取结果,字段级存储)"""
    __tablename__ = 'contract_fields'

    # ---------- 字段名枚举(8 个,与 LLM 输出契约一致) ----------
    # 顺序固定,前端展示按此顺序
    FIELD_NAMES = (
        'contract_no',      # 合同编号
        'contract_name',    # 合同名称
        'party_a',          # 甲方
        'party_b',          # 乙方
        'amount',           # 合同金额
        'sign_date',        # 签署日期
        'payment_method',   # 付款方式
        'valid_period',     # 有效期
    )

    # 字段中文标签(供前端展示 / 日志)
    FIELD_LABELS = {
        'contract_no': '合同编号',
        'contract_name': '合同名称',
        'party_a': '甲方',
        'party_b': '乙方',
        'amount': '合同金额',
        'sign_date': '签署日期',
        'payment_method': '付款方式',
        'valid_period': '有效期',
    }

    # ---------- 字段 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('analysis_tasks.id'),
                        nullable=False, index=True)
    field_name = db.Column(db.String(64), nullable=False)
    field_value = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    source_text = db.Column(db.Text, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ---------- 关系 ----------
    contract = db.relationship(
        'Contract',
        backref=db.backref('fields', lazy='dynamic')
    )
    task = db.relationship(
        'AnalysisTask',
        backref=db.backref('fields', lazy='dynamic')
    )

    # ---------- 唯一约束 ----------
    # 同一任务下同一字段名唯一(防止 save Stage 重复写入)
    __table_args__ = (
        db.UniqueConstraint('contract_id', 'field_name', 'task_id',
                            name='uq_contract_field_task'),
    )

    # ---------- 序列化 ----------
    def to_dict(self):
        """转为 dict"""
        return {
            'id': self.id,
            'contract_id': self.contract_id,
            'task_id': self.task_id,
            'field_name': self.field_name,
            'field_label': self.FIELD_LABELS.get(self.field_name, self.field_name),
            'field_value': self.field_value,
            'confidence': round(self.confidence, 4) if self.confidence is not None else 0.0,
            'source_text': self.source_text,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }

    def __repr__(self):
        return f'<ContractField {self.field_name}={self.field_value!r} (conf={self.confidence})>'
