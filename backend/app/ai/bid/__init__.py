"""
Bid AI 包(Sprint 7 - v0.9.0)

职责:
- 招标文件解析 Pipeline(requirement_extractor + pipeline)
- 投标生成 Agent(ReAct 循环,5 Tool)
- Word 渲染(proposal_renderer)

复用清单(只读 import,不修改):
- Sprint 3:extract_text_from_pdf / extract_text_using_deepseek_ocr / clean_text
- Sprint 4:SemanticChunker / vector_store_registry / rag_service._build_context_and_references
- Sprint 5:BaseTool / ToolRegistry / call_deepseek / _safe_serialize
- Sprint 6:ReAct 循环结构 / Word 渲染模式 / 单事务 Service 模式

导出:
- ProposalContext:Agent 执行上下文
- ProposalResult:Agent 执行结果
- ProposalAgent:ReAct 循环主体
- extract_requirements:需求提取函数
- run_bid_pipeline:Pipeline 入口
- render_proposal:Word 渲染函数
"""
from .context import ProposalContext
from .result import ProposalResult
from .requirement_extractor import extract_requirements
from .pipeline import run_bid_pipeline

# 延迟导入 ProposalAgent / render_proposal(避免循环依赖,运行时按需 import)


__all__ = [
    'ProposalContext',
    'ProposalResult',
    'ProposalAgent',
    'extract_requirements',
    'run_bid_pipeline',
    'render_proposal',
]


def __getattr__(name):
    """延迟导入 ProposalAgent / render_proposal(避免循环依赖)"""
    if name == 'ProposalAgent':
        from .proposal_agent import ProposalAgent
        return ProposalAgent
    if name == 'render_proposal':
        from .proposal_renderer import render_proposal
        return render_proposal
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
