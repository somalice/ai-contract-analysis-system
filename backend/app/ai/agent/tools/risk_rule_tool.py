"""
Tool3:规则化风险检查工具(Sprint 5 - v0.7.0)

职责:
- 基于合同字段(8 个)+ 合同全文,做规则化风险检查
- 确定性代码,不调 LLM(符合 user_rules §6 "规则优先于 LLM")

规则清单(11 条,覆盖 4 类风险):
- 付款风险:R001(付款方式缺失)/ R002(付款周期过长 ≥90 天)
- 金额风险:R003(金额缺失)/ R004(金额无法解析/为 0)
- 期限风险:R005(有效期缺失)/ R006(签署日期缺失/异常)/ R007(有效期与签署日矛盾)
- 关键条款缺失:R008(违约责任)/ R009(争议解决)/ R010(主体缺失)/ R011(合同期限)

每条风险输出:
- rule_id / type / severity / description / suggestion / evidence
"""
import re
from datetime import datetime

from app.ai.agent.context import AgentContext
from app.ai.agent.tools.base import BaseTool
from app.extensions.logger import logger


# ---------- 风险严重度 ----------
SEVERITY_HIGH = 'high'
SEVERITY_MEDIUM = 'medium'
SEVERITY_LOW = 'low'

# ---------- 风险类型 ----------
TYPE_PAYMENT = '付款风险'
TYPE_AMOUNT = '金额风险'
TYPE_PERIOD = '期限风险'
TYPE_MISSING = '关键条款缺失'

# ---------- 阈值 ----------
PAYMENT_DAYS_THRESHOLD = 90  # 付款周期 ≥90 天视为高风险


def _field_value(fields, name):
    """从 fields 列表中取指定字段名 的值"""
    for f in fields:
        if f.get('field_name') == name:
            val = f.get('field_value')
            if val is not None and str(val).strip():
                return str(val).strip()
            return None
    return None


def _parse_amount(value):
    """
    从金额字符串中解析数值
    支持:"人民币 100000 元" / "100,000.00" / "¥1,000,000" / "10.5 万"
    :return: float 或 None(无法解析)
    """
    if not value:
        return None
    text = str(value).strip()
    # 去除千分位逗号
    text_clean = text.replace(',', '').replace('，', '')
    # 匹配数字(含小数)
    m = re.search(r'(\d+(?:\.\d+)?)', text_clean)
    if not m:
        return None
    try:
        amount = float(m.group(1))
    except (ValueError, TypeError):
        return None
    # "万" 单位换算
    if '万' in text_clean:
        amount *= 10000
    return amount


def _extract_payment_days(value):
    """
    从付款方式文本中提取付款周期天数
    支持:"月结 30 天" / "验收后 90 天" / "60 个工作日内付款" / "收到发票后 45 天"
    :return: int 或 None(未识别到周期)
    """
    if not value:
        return None
    text = str(value)
    # 匹配 "N 天" / "N 个工作日" / "月结 N 天"
    patterns = [
        r'月结\s*(\d+)\s*天',
        r'验收后\s*(\d+)\s*天',
        r'收到发票后\s*(\d+)\s*天',
        r'(\d+)\s*个工作日',
        r'(\d+)\s*天内付款',
        r'付款周期\s*[:：]?\s*(\d+)\s*天',
        r'(\d+)\s*天',  # 兜底:N 天
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, TypeError):
                continue
    return None


def _parse_date(value):
    """
    解析日期字符串
    支持:"2026-07-15" / "2026/7/15" / "2026年7月15日"
    :return: datetime 或 None(无法解析)
    """
    if not value:
        return None
    text = str(value).strip()
    # 标准格式
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # 中文格式 "2026年7月15日"
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    # 仅年月 "2026年7月"
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    return None


def _has_keyword(text, keywords):
    """检查文本中是否包含任一关键词(小写化包含匹配)"""
    if not text:
        return False
    lower = text.lower()
    return any(kw in lower for kw in keywords)


class RiskRuleTool(BaseTool):
    """规则化风险检查工具(确定性,不调 LLM)"""

    @property
    def name(self) -> str:
        return 'risk_rule_tool'

    @property
    def description(self) -> str:
        return (
            '对合同做规则化风险检查(确定性规则,非 LLM)。检查 4 类风险:'
            '付款风险(付款方式缺失/周期过长)、金额风险(金额缺失/异常)、'
            '期限风险(有效期/签署日期缺失或矛盾)、关键条款缺失(违约责任/争议解决/主体等)。'
            '每条风险含类型、严重度、描述、依据与修改建议。无需参数。'
        )

    @property
    def args_schema(self) -> dict:
        return {}  # 无参数,从 ctx.fields + ctx.document_text 取

    def run(self, args: dict, ctx: AgentContext) -> dict:
        """
        执行规则化风险检查
        :return: {risks, count}
            - risks: [{rule_id, type, severity, description, suggestion, evidence}]
            - count: 风险数量
        """
        fields = ctx.fields or []
        doc_text = ctx.document_text or ''

        # 字段值提取
        payment_method = _field_value(fields, 'payment_method')
        amount = _field_value(fields, 'amount')
        valid_period = _field_value(fields, 'valid_period')
        sign_date = _field_value(fields, 'sign_date')
        party_a = _field_value(fields, 'party_a')
        party_b = _field_value(fields, 'party_b')

        risks = []

        # ========== 付款风险 ==========
        # R001:付款方式缺失
        if not payment_method:
            risks.append({
                'rule_id': 'R001',
                'type': TYPE_PAYMENT,
                'severity': SEVERITY_MEDIUM,
                'description': '合同未明确付款方式,存在付款条款模糊风险',
                'suggestion': '建议补充明确的付款方式、付款节点与付款周期',
                'evidence': '付款方式字段缺失',
            })
        else:
            # R002:付款周期过长
            days = _extract_payment_days(payment_method)
            if days is not None and days >= PAYMENT_DAYS_THRESHOLD:
                risks.append({
                    'rule_id': 'R002',
                    'type': TYPE_PAYMENT,
                    'severity': SEVERITY_HIGH,
                    'description': f'付款周期过长({days} 天),存在资金占用与回款风险',
                    'suggestion': f'建议缩短付款周期至 30 天以内,或增加预付款比例(当前:{payment_method})',
                    'evidence': payment_method,
                })

        # ========== 金额风险 ==========
        # R003:金额缺失
        if not amount:
            risks.append({
                'rule_id': 'R003',
                'type': TYPE_AMOUNT,
                'severity': SEVERITY_HIGH,
                'description': '合同未明确金额,存在重大条款缺失风险',
                'suggestion': '建议补充合同金额(含币种与大小写)',
                'evidence': '合同金额字段缺失',
            })
        else:
            # R004:金额无法解析 / 为 0
            amount_num = _parse_amount(amount)
            if amount_num is None:
                risks.append({
                    'rule_id': 'R004',
                    'type': TYPE_AMOUNT,
                    'severity': SEVERITY_HIGH,
                    'description': '合同金额无法解析为有效数值,可能存在金额表述异常',
                    'suggestion': '建议核实金额表述,确保包含明确数值与币种',
                    'evidence': amount,
                })
            elif amount_num == 0:
                risks.append({
                    'rule_id': 'R004',
                    'type': TYPE_AMOUNT,
                    'severity': SEVERITY_HIGH,
                    'description': '合同金额为 0,可能存在异常',
                    'suggestion': '建议核实合同金额是否正确',
                    'evidence': amount,
                })

        # ========== 期限风险 ==========
        # R005:有效期缺失
        if not valid_period:
            risks.append({
                'rule_id': 'R005',
                'type': TYPE_PERIOD,
                'severity': SEVERITY_MEDIUM,
                'description': '合同未明确有效期,存在期限不确定风险',
                'suggestion': '建议补充合同有效期或截止日期',
                'evidence': '有效期字段缺失',
            })

        # R006:签署日期缺失/异常
        sign_date_parsed = _parse_date(sign_date) if sign_date else None
        if not sign_date:
            risks.append({
                'rule_id': 'R006',
                'type': TYPE_PERIOD,
                'severity': SEVERITY_MEDIUM,
                'description': '合同未明确签署日期,存在时间节点不清风险',
                'suggestion': '建议补充合同签署日期',
                'evidence': '签署日期字段缺失',
            })
        elif sign_date_parsed is None:
            risks.append({
                'rule_id': 'R006',
                'type': TYPE_PERIOD,
                'severity': SEVERITY_LOW,
                'description': '签署日期格式异常,无法解析为标准日期',
                'suggestion': '建议规范签署日期格式(如 YYYY-MM-DD)',
                'evidence': sign_date,
            })

        # R007:有效期与签署日期矛盾(有效期早于签署日)
        if valid_period and sign_date_parsed:
            valid_date = _parse_date(valid_period)
            if valid_date is not None and valid_date < sign_date_parsed:
                risks.append({
                    'rule_id': 'R007',
                    'type': TYPE_PERIOD,
                    'severity': SEVERITY_HIGH,
                    'description': '合同有效期早于签署日期,存在期限矛盾',
                    'suggestion': '建议核实有效期与签署日期,确保有效期晚于签署日',
                    'evidence': f'签署日期:{sign_date},有效期:{valid_period}',
                })

        # ========== 关键条款缺失 ==========
        # R008:违约责任
        if not _has_keyword(doc_text, ['违约责任', '违约金', '违约条款', '承担违约']):
            risks.append({
                'rule_id': 'R008',
                'type': TYPE_MISSING,
                'severity': SEVERITY_HIGH,
                'description': '合同全文未体现违约责任条款,存在违约救济缺失风险',
                'suggestion': '建议补充违约责任条款(含违约金计算方式与救济途径)',
                'evidence': '全文未检索到"违约责任/违约金"关键词',
            })

        # R009:争议解决
        if not _has_keyword(doc_text, ['争议解决', '仲裁', '诉讼', '管辖法院', '纠纷解决']):
            risks.append({
                'rule_id': 'R009',
                'type': TYPE_MISSING,
                'severity': SEVERITY_MEDIUM,
                'description': '合同全文未体现争议解决条款,存在纠纷处理机制缺失风险',
                'suggestion': '建议补充争议解决条款(约定仲裁机构或管辖法院)',
                'evidence': '全文未检索到"争议解决/仲裁/诉讼"关键词',
            })

        # R010:主体缺失
        if not party_a or not party_b:
            missing = []
            if not party_a:
                missing.append('甲方')
            if not party_b:
                missing.append('乙方')
            risks.append({
                'rule_id': 'R010',
                'type': TYPE_MISSING,
                'severity': SEVERITY_HIGH,
                'description': f'合同主体缺失({"、".join(missing)}),存在主体不明风险',
                'suggestion': '建议补充完整的合同主体信息(甲乙方全称)',
                'evidence': f'缺失主体:{"、".join(missing)}',
            })

        # R011:合同期限
        if not _has_keyword(doc_text, ['合同期限', '有效期', '期限', '起至', '生效日期']):
            risks.append({
                'rule_id': 'R011',
                'type': TYPE_MISSING,
                'severity': SEVERITY_LOW,
                'description': '合同全文未体现合同期限条款',
                'suggestion': '建议补充合同期限条款(起止日期)',
                'evidence': '全文未检索到"合同期限/有效期"关键词',
            })

        logger.info('[Agent:risk_rule_tool] 规则检查完成: risks=%s', len(risks))

        return {
            'risks': risks,
            'count': len(risks),
        }
