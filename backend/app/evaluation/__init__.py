"""
AI 验收评估模块(Sprint 8.5 - v1.0.0 Release Candidate)

职责:
- 封版前 AI 质量验收(只读,不修改业务数据/不修改 RAG 链路)
- RAG 能力评估: Faithfulness / Answer Relevancy / Context Precision / Context Recall
- AI 调用日志质量分析: 稳定性 / 性能(P95) / Token 消耗
- Agent 工具调用统计: contract_review / generation / bid

约束(重要):
- 不修改已有业务逻辑
- 不修改数据库表结构
- 不修改 RAG 核心链路(Embedding/VectorStore/Retriever/LLM均复用现有组件)
- 不升级 LangChain
- 所有新增代码独立在本模块

目录:
- datasets/: 测试数据集(contract_qa_dataset.json)
- metrics/: 评估指标实现(rag_metrics, ai_metrics)
- runners/: 评估运行器(run_rag_eval)
- reports/: 报告生成说明
- config.py: 评估配置(阈值/目标值)
"""
from .config import EVAL_CONFIG

__all__ = ['EVAL_CONFIG']
