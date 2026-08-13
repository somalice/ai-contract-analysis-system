"""
Tool1:合同字段查询工具(Sprint 5 - v0.7.0)

职责:
- 查询合同的结构化字段(8 个:合同编号/名称/甲乙方/金额/签署日期/付款方式/有效期)
- 只读复用 Sprint 3 的 analysis_service.get_contract_fields(不修改 Sprint 3)

复用安全性:
- Agent 由 review_service 调用,该 service 已在 API 层 @role_required + Service 层权限校验后执行
- 传 current_user=None:analysis_service._check_contract_permission 仅对 employee 生效,
  None 时跳过,不绕过任何既有校验(API 层已拦截 employee 触发审核)

确定性:✅ 纯 DB 查询,不调 LLM
"""
from app.ai.agent.context import AgentContext
from app.ai.agent.tools.base import BaseTool
from app.services import analysis_service


class ContractFieldTool(BaseTool):
    """合同字段查询工具(查询 8 个结构化字段)"""

    @property
    def name(self) -> str:
        return 'contract_field_tool'

    @property
    def description(self) -> str:
        return (
            '查询当前合同的结构化字段(8 个:合同编号、合同名称、甲方、乙方、'
            '合同金额、签署日期、付款方式、有效期)。每个字段含字段值、置信度、来源文本。'
            '缺失字段返回 null。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}  # 无参数,从 ctx.contract_id 取

    def run(self, args: dict, ctx: AgentContext) -> dict:
        """
        查询合同字段
        :return: {fields, source, task}
            - fields: 字段列表 [{field_name, field_label, field_value, confidence, source_text}]
            - source: 数据来源 'contract_fields' / 'legacy_json' / 'empty'
            - task: 最近分析任务 {id, task_no, status}(可能为 null)
        """
        result = analysis_service.get_contract_fields(
            ctx.contract_id, current_user=None
        )

        fields = result.get('fields', [])
        # 统计非空字段数(供 LLM 快速判断字段完整性)
        non_null_count = sum(
            1 for f in fields if f.get('field_value')
        )

        return {
            'fields': fields,
            'source': result.get('source', 'empty'),
            'task': result.get('task'),
            'field_count': len(fields),
            'non_null_count': non_null_count,
            'missing_count': len(fields) - non_null_count,
        }
