"""
Tool3:企业资料查询工具(Sprint 7 - v0.9.0)

职责:
- 返回企业资料(公司简介 / 资质 / 业绩)
- 供 LLM 了解企业可用资料,决策生成哪些资质章节

数据来源:ctx.company_profile(由 proposal_service 预加载,
来自 knowledge_type='company' 的 KnowledgeDocument 列表)

约束:从 ctx.company_profile 读,无参数,不调 LLM,不访问 DB
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.bid.context import ProposalContext


class CompanyProfileTool(BaseTool):
    """企业资料查询工具"""

    @property
    def name(self) -> str:
        return 'company_profile_tool'

    @property
    def description(self) -> str:
        return (
            '查询投标方企业资料。返回公司简介、资质清单、业绩案例、项目团队等。'
            '用于了解可用的企业资质与业绩,生成资质文件章节。'
            '若企业资料未上传(knowledge_type=company 为空),返回 available=false,'
            'Agent 应生成通用资质章节(用"详见附件资质证书"占位)。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}

    def run(self, args: dict, ctx: ProposalContext) -> dict:
        """
        查询企业资料
        :return: {available, company_name, brief, qualifications, past_projects, source_count}
        """
        company_profile = ctx.company_profile or {}

        # company_profile 结构(由 proposal_service 预加载):
        # {
        #   'available': bool,
        #   'company_name': str,           # 从第一个 company 文档标题推断
        #   'brief': str,                  # 公司简介(拼接前 N 字)
        #   'qualifications': [str],       # 资质清单
        #   'past_projects': [str],        # 业绩案例
        #   'source_documents': [{id, doc_no, title}],  # 来源文档
        #   'source_count': int
        # }
        available = company_profile.get('available', False)

        return {
            'available': available,
            'company_name': company_profile.get('company_name', ''),
            'brief': company_profile.get('brief', ''),
            'qualifications': company_profile.get('qualifications', []),
            'past_projects': company_profile.get('past_projects', []),
            'source_documents': company_profile.get('source_documents', []),
            'source_count': company_profile.get('source_count', 0),
            'note': '' if available else '企业资料未上传(knowledge_type=company 为空),生成通用资质章节',
        }
