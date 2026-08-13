"""
AI 调用日志模型(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

对应表 ai_request_logs:记录每一次 Agent / RAG 对大模型的调用统计(聚合级,非每轮 LLM 调用)。
- 聚合粒度:一次审核(ContractReviewAgent.run)→ 1 条记录,含 trace_summary(多轮 LLM + Tool 汇总)
- RAG 问答:一次 rag_service.query_rag → 1 条记录

约束:
- 全部字段 nullable(除 id/created_time/status/agent_type)。日志记录失败不阻断业务,落库失败仅 warning。
- to_dict() 不包含敏感信息(无 input_text/output_text,仅 token 数与结果摘要)。
- foreign key users 无 cascade(用户删除后 user_id 保留为 FK id,仅关系消失)。
"""
from datetime import datetime
from app.extensions.db import db


VALID_STATUS = ('success', 'failed')
VALID_AGENT_TYPES = (
    'contract_review',   # Sprint 5 ContractReviewAgent
    'generation',        # Sprint 6 GenerationAgent
    'bid',               # Sprint 7 Bid/ProposalAgent
    'rag',               # Sprint 4 RAG Query
)


class AIRequestLog(db.Model):
    """AI 调用日志"""
    __tablename__ = 'ai_request_logs'

    # ---------- 主键 / 追踪 ----------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ---------- 主体 ----------
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    agent_type = db.Column(db.String(32), nullable=False, index=True)  # VALID_AGENT_TYPES
    model = db.Column(db.String(64), nullable=True)                    # deepseek-chat 等
    prompt_version = db.Column(db.String(32), nullable=True)           # contract_review_v1 / bid_proposal_v1 等
    # ---------- Token 用量(从 response.usage_metadata 或 contextvar 累计)----------
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    total_tokens = db.Column(db.Integer, nullable=True)
    # ---------- 性能 ----------
    latency_ms = db.Column(db.Integer, nullable=True, index=True)
    # ---------- 结果 ----------
    status = db.Column(db.String(16), nullable=False, default='success', index=True)  # success / failed
    error_message = db.Column(db.Text, nullable=True)
    # 完整 trace_summary(含 tool_stats/llm_stats/iterations 等 10 项指标;RAG 可能为 None)
    trace_summary = db.Column(db.JSON, nullable=True)
    # ---------- 关联业务对象(按需)----------
    related_id = db.Column(db.Integer, nullable=True, index=True)       # review_id / generation_id / proposal_id
    related_type = db.Column(db.String(32), nullable=True)             # review / generation / proposal
    # ---------- 时间戳 ----------
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # ---------- 关系 ----------
    user = db.relationship('User', lazy='joined')

    # ---------- 序列化 ----------
    def to_dict(self, include_trace_summary=True):
        d = {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'agent_type': self.agent_type,
            'model': self.model,
            'prompt_version': self.prompt_version,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'latency_ms': self.latency_ms,
            'status': self.status,
            'error_message': self.error_message,
            'related_id': self.related_id,
            'related_type': self.related_type,
            'created_time': self.created_time.strftime('%Y-%m-%d %H:%M:%S') if self.created_time else None,
        }
        if include_trace_summary:
            d['trace_summary'] = self.trace_summary
        return d

    def __repr__(self):
        return (
            f'<AIRequestLog id={self.id} type={self.agent_type} '
            f'status={self.status} tokens={self.total_tokens or 0}>'
        )
