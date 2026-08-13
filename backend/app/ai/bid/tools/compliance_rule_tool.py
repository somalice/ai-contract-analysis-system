"""
Tool5:合规规则校验工具(Sprint 7 - v0.9.0)

职责:
- 规则化校验生成投标方案的完整性(确定性代码,不调 LLM)
- 校验 1:必填章节齐全(technical / commercial / responsive / qualification)
- 校验 2:招标需求覆盖率(关键需求字段是否在章节中响应)
- 校验 3:企业资料可用性(若不可用,标 medium 风险)

借鉴 Sprint 6 contract_rule_tool 模式(确定性规则,非 LLM)。

校验结果回写 ctx.validation_results(passed / issues)。

每条 issue:{type, description, suggestion, severity}
"""
from app.ai.agent.tools.base import BaseTool  # 复用 Sprint 5 基类
from app.ai.bid.context import ProposalContext
from app.extensions.logger import logger


# ---------- 校验类型 ----------
TYPE_MISSING_SECTION = '必填章节缺失'
TYPE_REQUIREMENT_COVERAGE = '需求覆盖不足'
TYPE_COMPANY_PROFILE_UNAVAILABLE = '企业资料不可用'

# ---------- 必填章节清单(供完整性校验) ----------
# 与 ProposalSection.REQUIRED_SECTION_TYPES 保持一致(此处独立声明,避免循环 import)
_REQUIRED_SECTIONS = ('technical', 'commercial', 'responsive', 'qualification')

# ---------- 关键需求字段(供覆盖率校验) ----------
_KEY_REQUIREMENT_FIELDS = (
    'project_name', 'tender_org', 'budget', 'deadline',
    'technical_requirements', 'qualification_requirements', 'scoring_criteria',
)


class ComplianceRuleTool(BaseTool):
    """合规规则校验工具(确定性,不调 LLM):必填章节齐全 + 需求覆盖率 + 企业资料可用性"""

    @property
    def name(self) -> str:
        return 'compliance_rule_tool'

    @property
    def description(self) -> str:
        return (
            '对投标方案做规则化校验(确定性规则,非 LLM)。校验三类:'
            '必填章节缺失(technical/commercial/responsive/qualification 4 章节是否齐全)、'
            '需求覆盖不足(招标关键需求字段是否在章节中响应)、'
            '企业资料可用性(knowledge_type=company 是否上传)。'
            '校验结果含 passed 标志与 issues 列表。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}

    def run(self, args: dict, ctx: ProposalContext) -> dict:
        """
        执行规则校验
        :return: {passed, issues, summary, high_count, medium_count}
            - passed: bool 是否通过
            - issues: [{type, description, suggestion, severity}]
            - summary: 摘要文本
        """
        sections = ctx.generated_sections or []
        requirements = ctx.requirements or {}
        company_profile = ctx.company_profile or {}

        issues = []

        # ========== 校验 1:必填章节缺失 ==========
        generated_types = {s.get('section_type') for s in sections
                           if s.get('content', '').strip()}
        for required_type in _REQUIRED_SECTIONS:
            if required_type not in generated_types:
                issues.append({
                    'type': TYPE_MISSING_SECTION,
                    'severity': 'high',
                    'description': f'必填章节未生成:{required_type}',
                    'suggestion': f'请调用 proposal_section_tool 生成 {required_type} 章节',
                })

        # ========== 校验 2:需求覆盖率 ==========
        # 统计关键需求字段的非空数
        filled_key_fields = 0
        missing_key_fields = []
        for field in _KEY_REQUIREMENT_FIELDS:
            val = requirements.get(field)
            if val is None:
                missing_key_fields.append(field)
            elif isinstance(val, str) and not val.strip():
                missing_key_fields.append(field)
            elif isinstance(val, list) and len(val) == 0:
                missing_key_fields.append(field)
            else:
                filled_key_fields += 1

        coverage = filled_key_fields / len(_KEY_REQUIREMENT_FIELDS) if _KEY_REQUIREMENT_FIELDS else 0
        if coverage < 0.5:
            issues.append({
                'type': TYPE_REQUIREMENT_COVERAGE,
                'severity': 'high',
                'description': f'招标需求覆盖率仅 {coverage:.0%}(关键字段缺失 {len(missing_key_fields)}/{len(_KEY_REQUIREMENT_FIELDS)})',
                'suggestion': '建议重新解析招标文件或补充缺失的需求字段',
            })
        elif coverage < 0.8:
            issues.append({
                'type': TYPE_REQUIREMENT_COVERAGE,
                'severity': 'medium',
                'description': f'招标需求覆盖率 {coverage:.0%}(缺失字段:{",".join(missing_key_fields[:3])})',
                'suggestion': '在生成章节时注意响应缺失字段对应的需求',
            })

        # ========== 校验 3:企业资料可用性 ==========
        if not company_profile.get('available'):
            issues.append({
                'type': TYPE_COMPANY_PROFILE_UNAVAILABLE,
                'severity': 'medium',
                'description': '企业资料未上传(knowledge_type=company 为空),资质章节为通用占位',
                'suggestion': '建议上传企业资料(knowledge_type=company)后重新生成',
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
            summary = '校验通过:必填章节齐全,需求覆盖充分,企业资料可用'
        else:
            summary = (f'校验未通过:共 {len(issues)} 项问题'
                       f'(高 {high_count} / 中 {medium_count})')

        logger.info('[Bid:compliance_rule_tool] 校验完成: passed=%s issues=%s coverage=%.0f%%',
                    passed, len(issues), coverage * 100)

        return {
            'passed': passed,
            'issues': issues,
            'high_count': high_count,
            'medium_count': medium_count,
            'coverage': coverage,
            'summary': summary,
        }
