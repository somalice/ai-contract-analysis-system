"""
Tool1:模板变量查询工具(Sprint 6 - v0.8.0)

职责:
- 返回模板变量清单(变量名 / label / required / sample)+ 必填项缺失情况
- 供 LLM 了解可填充项与缺失项,决策是否需要补充条款

约束:从 ctx.template + ctx.input_variables 读,无参数,不调 LLM
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.generation.context import GenerationContext


class TemplateTool(BaseTool):
    """模板变量查询工具"""

    @property
    def name(self) -> str:
        return 'template_tool'

    @property
    def description(self) -> str:
        return (
            '查询当前合同模板的变量清单与填写情况。返回所有变量(name/label/required/sample)、'
            '用户已填写的值、缺失的必填项。用于了解模板结构、判断是否需补充条款。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}

    def run(self, args: dict, ctx: GenerationContext) -> dict:
        """
        查询模板变量与填写情况
        :return: {template_name, contract_type, variables, filled, missing_required}
            - variables: [{name, label, required, sample, filled_value}]
            - filled: 已填写变量数
            - missing_required: 缺失的必填项 [{name, label}]
        """
        template = ctx.template or {}
        template_vars = template.get('variables') or []
        input_vars = ctx.input_variables or {}

        variables = []
        missing_required = []
        filled_count = 0

        for v in template_vars:
            vname = v.get('name', '')
            filled_value = input_vars.get(vname)
            is_filled = filled_value is not None and str(filled_value).strip() != ''
            if is_filled:
                filled_count += 1
            variables.append({
                'name': vname,
                'label': v.get('label', vname),
                'required': v.get('required', True),
                'sample': v.get('sample', ''),
                'filled_value': filled_value if is_filled else None,
                'is_filled': is_filled,
            })
            # 缺失的必填项
            if v.get('required', True) and not is_filled:
                missing_required.append({
                    'name': vname,
                    'label': v.get('label', vname),
                })

        return {
            'template_name': template.get('name', ''),
            'contract_type': template.get('contract_type', ctx.contract_type),
            'variable_count': len(variables),
            'filled_count': filled_count,
            'missing_required': missing_required,
            'missing_required_count': len(missing_required),
            'variables': variables,
        }
