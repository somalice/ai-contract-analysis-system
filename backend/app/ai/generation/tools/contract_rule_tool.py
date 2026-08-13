"""
Tool4:合同规则校验工具(Sprint 6 - v0.8.1)

职责:
- 规则化校验生成合同的完整性(确定性代码,不调 LLM)
- 校验 1:必填变量是否齐全(缺失字段检查)
- 校验 2:关键条款是否齐备(付款/违约/保密 等核心条款是否已生成,风险条款检查)

借鉴 Sprint 5 risk_rule_tool 模式(确定性规则,非 LLM)。

校验结果回写 ctx.validation_results(passed / issues)。

每条 issue:{type, description, suggestion, severity}

命名说明:v0.8.1 起 Tool 名从 rule_validation_tool 对齐为 contract_rule_tool
(与用户补充要求一致:contract_rule_tool 检查缺失字段和风险条款)。
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.generation.context import GenerationContext
from app.extensions.logger import logger


# ---------- 校验类型 ----------
TYPE_MISSING_VARIABLE = '必填变量缺失'
TYPE_MISSING_CLAUSE = '关键条款缺失'

# ---------- 关键条款清单(用于完整性校验) ----------
# 每项:关键词列表(匹配 generated_clauses.name,大小写不敏感包含)
_KEY_CLAUSES = [
    {
        'name': '付款条款',
        'keywords': ['付款', '支付', '结算'],
        'severity': 'high',
        'suggestion': '建议补充付款条款(含付款方式、节点、周期)',
    },
    {
        'name': '违约责任',
        'keywords': ['违约', '违约责任', '违约金'],
        'severity': 'high',
        'suggestion': '建议补充违约责任条款(含违约金计算与救济途径)',
    },
    {
        'name': '保密条款',
        'keywords': ['保密', '保密义务'],
        'severity': 'medium',
        'suggestion': '建议补充保密条款(含保密范围与期限)',
    },
    {
        'name': '争议解决',
        'keywords': ['争议', '争议解决', '仲裁', '诉讼', '管辖'],
        'severity': 'medium',
        'suggestion': '建议补充争议解决条款(约定仲裁或管辖法院)',
    },
]


class ContractRuleTool(BaseTool):
    """合同规则校验工具(确定性,不调 LLM):检查缺失字段和风险条款"""

    @property
    def name(self) -> str:
        return 'contract_rule_tool'

    @property
    def description(self) -> str:
        return (
            '对合同生成结果做规则化校验(确定性规则,非 LLM)。校验两类:'
            '必填变量缺失(模板声明的 required 变量未填写)、关键条款缺失'
            '(付款/违约/保密/争议解决等核心条款未生成)。'
            '校验结果含 passed 标志与 issues 列表。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}

    def run(self, args: dict, ctx: GenerationContext) -> dict:
        """
        执行规则校验
        :return: {passed, issues, summary}
            - passed: bool 是否通过
            - issues: [{type, description, suggestion, severity}]
            - summary: 摘要文本
        """
        template = ctx.template or {}
        template_vars = template.get('variables') or []
        input_vars = ctx.input_variables or {}
        clauses = ctx.generated_clauses or []

        issues = []

        # ========== 校验 1:必填变量缺失 ==========
        for v in template_vars:
            if not v.get('required', True):
                continue
            vname = v.get('name', '')
            val = input_vars.get(vname)
            if val is None or str(val).strip() == '':
                issues.append({
                    'type': TYPE_MISSING_VARIABLE,
                    'severity': 'high',
                    'description': f'必填变量"{vname}"({v.get("label", vname)})未填写',
                    'suggestion': f'请填写变量 {vname} 后再生成',
                })

        # ========== 校验 2:关键条款缺失 ==========
        # 已生成的条款名(clause.name)
        clause_names = [str(c.get('name', '')).lower() for c in clauses]
        # 同时考虑模板变量是否已含相关字段(如 payment_method 已填则视为有付款信息)
        # 简化:仅检查 generated_clauses,模板变量由校验1覆盖

        for kc in _KEY_CLAUSES:
            # 检查是否已生成该类条款
            found = any(
                any(kw.lower() in cn for kw in kc['keywords'])
                for cn in clause_names
            )
            if not found:
                issues.append({
                    'type': TYPE_MISSING_CLAUSE,
                    'severity': kc['severity'],
                    'description': f'未生成关键条款:{kc["name"]}',
                    'suggestion': kc['suggestion'],
                })

        passed = len(issues) == 0

        # 回写 ctx.validation_results
        ctx.validation_results = {
            'passed': passed,
            'issues': issues,
        }

        # 汇总
        high_count = sum(1 for i in issues if i.get('severity') == 'high')
        medium_count = sum(1 for i in issues if i.get('severity') == 'medium')
        if passed:
            summary = '校验通过:必填变量齐全,关键条款齐备'
        else:
            summary = (f'校验未通过:共 {len(issues)} 项问题'
                       f'(高 {high_count} / 中 {medium_count})')

        logger.info('[Gen:contract_rule_tool] 校验完成: passed=%s issues=%s',
                    passed, len(issues))

        return {
            'passed': passed,
            'issues': issues,
            'high_count': high_count,
            'medium_count': medium_count,
            'summary': summary,
        }
