"""
AI 评估报告快照模型(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

对应表 evaluation_reports:每次 POST /evaluation/report 生成的指标快照持久化。
metrics 为完整 JSON:包含 rag/agent/tool/cost/operation 五大指标聚合。

指标来源(全部只读复用已有表,不写新数据):
- rag/agent/cost: ai_request_logs(按 agent_type / status 聚合)
- tool: review_reports / generated_contracts / generated_proposals 的 trace_summary.tool_stats 聚合
- operation: operation_logs(按 operation_type 聚合)
"""
import uuid
from datetime import datetime
from app.extensions.db import db


def _generate_report_no():
    """生成报告编号:EVAL-YYYYMMDDHHMMSS-XXXXXXXX"""
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'EVAL-{timestamp}-{suffix}'


class EvaluationReport(db.Model):
    """AI 评估报告快照"""
    __tablename__ = 'evaluation_reports'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_no = db.Column(db.String(64), unique=True, nullable=False, index=True, default=_generate_report_no)

    # 统计区间
    period_start = db.Column(db.DateTime, nullable=True)
    period_end = db.Column(db.DateTime, nullable=True)

    # 完整指标快照(JSON):
    # {
    #   rag: {call_count, success_count, failed_count, success_rate, avg_latency_ms, p95_latency_ms, avg_total_tokens},
    #   agent: {
    #       contract_review: {total, success, failed, success_rate, avg_latency_ms, avg_tokens},
    #       generation: {...},
    #       bid: {...},
    #   },
    #   tool: {total_calls, success, failed, success_rate,
    #          breakdown: [{tool, calls, success, failed, success_rate, total_duration_ms}]},
    #   cost: {input_tokens, output_tokens, total_tokens, estimated_rmb},
    #   operation: {total, failed, failure_rate,
    #               breakdown: [{operation_type, count, failed, failure_rate}]}
    # }
    metrics = db.Column(db.JSON, nullable=False)

    summary = db.Column(db.Text, nullable=True)

    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # ---------- 关系 ----------
    creator = db.relationship('User', lazy='joined')

    # ---------- 序列化 ----------
    def to_dict(self, include_metrics=True):
        d = {
            'id': self.id,
            'report_no': self.report_no,
            'period_start': self.period_start.strftime('%Y-%m-%d %H:%M:%S') if self.period_start else None,
            'period_end': self.period_end.strftime('%Y-%m-%d %H:%M:%S') if self.period_end else None,
            'summary': self.summary,
            'generated_by': self.generated_by,
            'generated_by_username': self.creator.username if self.creator else None,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }
        if include_metrics:
            d['metrics'] = self.metrics
        return d

    def __repr__(self):
        return f'<EvaluationReport id={self.id} no={self.report_no}>'
