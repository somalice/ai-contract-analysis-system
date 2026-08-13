"""
Tool1:招标需求查询工具(Sprint 7 - v0.9.0)

职责:
- 返回招标需求 15 字段 + 缺失项 + 置信度
- 供 LLM 了解招标需求与缺失项,决策生成哪些章节

约束:从 ctx.requirements 读,无参数,不调 LLM,不访问 DB
镜像:Sprint 6 TemplateTool(从 ctx.template 读)
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.bid.context import ProposalContext


class RequirementTool(BaseTool):
    """招标需求查询工具"""

    @property
    def name(self) -> str:
        return 'requirement_tool'

    @property
    def description(self) -> str:
        return (
            '查询当前招标文件的需求字段。返回 15 个核心字段(项目名称/招标单位/预算/截止时间/'
            '技术要求/资格要求/评分标准等)、已提取字段数、缺失字段清单与整体置信度。'
            '用于了解招标要求、判断投标方案应覆盖哪些技术点与资质要求。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}

    def run(self, args: dict, ctx: ProposalContext) -> dict:
        """
        查询招标需求
        :return: {project_name, tender_org, budget, deadline, requirement_data,
                  field_count, missing_count, missing_fields, confidence}
        """
        requirements = ctx.requirements or {}
        # 15 字段列表(来自 BidRequirement.REQUIRED_FIELDS,此处不直接依赖 Model 避免循环)
        all_fields = (
            'project_name', 'tender_org', 'project_location', 'budget', 'deadline',
            'duration', 'delivery_requirements', 'technical_requirements',
            'qualification_requirements', 'scoring_criteria', 'bid_opening_time',
            'bid_validity', 'payment_terms', 'contact', 'other',
        )

        # 缺失字段(仅返回字段名,避免响应过大)
        missing_fields = []
        for field in all_fields:
            val = requirements.get(field)
            if val is None:
                missing_fields.append(field)
            elif isinstance(val, str) and not val.strip():
                missing_fields.append(field)
            elif isinstance(val, list) and len(val) == 0:
                missing_fields.append(field)

        field_count = len(all_fields) - len(missing_fields)

        return {
            'project_name': requirements.get('project_name'),
            'tender_org': requirements.get('tender_org'),
            'budget': requirements.get('budget'),
            'deadline': requirements.get('deadline'),
            'duration': requirements.get('duration'),
            'bid_validity': requirements.get('bid_validity'),
            'payment_terms': requirements.get('payment_terms'),
            'technical_requirements': requirements.get('technical_requirements') or [],
            'qualification_requirements': requirements.get('qualification_requirements') or [],
            'scoring_criteria': requirements.get('scoring_criteria') or [],
            'delivery_requirements': requirements.get('delivery_requirements'),
            'contact': requirements.get('contact'),
            'other': requirements.get('other'),
            'field_count': field_count,
            'missing_count': len(missing_fields),
            'missing_fields': missing_fields,
            'confidence': requirements.get('confidence'),
            'total_fields': len(all_fields),
        }
