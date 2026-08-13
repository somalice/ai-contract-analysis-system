"""
Sprint 8.9 知识覆盖判定模块

核心概念分离:
- Retriever Hit: 检索召回到了内容(召回非空 / 命中文档数 > 0)
- Knowledge Coverage: 召回到了能支撑答案核心事实的"正确知识"

判定基于多信号综合(不使用单一字符串/Jaccard):
1. 语义相似度信号: sim(ground_truth, chunk) 取检索 context 内最大 chunk 相似度
2. 实体/数字/关键词信号: ground_truth 中的关键事实(数字+单位、法律术语、核心概念)
   在检索 context 中的出现比例
3. 文档来源信号: source_document(数据集标注的期望来源文档) 与命中文档的标题对齐

四态输出:
- covered    : 知识库存在能支撑答案核心事实的内容
- partial    : 知识库只能支撑部分答案
- not_covered: 知识库不存在相关知识
- unknown    : 无法判断(如无检索上下文等异常)

约束(用户规则):
- 禁止为了指标修改阈值: 判定阈值仅用于诊断分类,不参与 RAG 4 项指标计算
- 不降低指标目标 / 不修改 ground_truth / 不删除低分问题
- 复用已有 retrieval 结果与 sim_fn, 不重复 embedding / rerank / LLM
"""
from __future__ import annotations

import re
from typing import Dict, Any, List, Optional, Callable

# ============================================================
# 实体/事实提取(用于知识覆盖判定的关键词信号)
# ============================================================

# 法律/合同核心术语表(出现即视为强知识信号)
_TERM_TABLE = [
    # 法律概念
    '提存', '让与担保', '情势变更', '诉讼时效', '撤销权', '附随义务', '不安抗辩权',
    '定金罚则', '定金', '违约金', '不可抗力', '所有权保留', '瑕疵担保', '债权转让',
    '债务转让', '阴阳合同', '黑白合同', '竞业限制', '保密义务', '保密期限',
    '管辖法院', '专属管辖', '仲裁', '准据法', '最密切联系', '公证', '流押',
    '显失公平', '重大误解', '欺诈', '胁迫', '恶意串通', '公序良俗', '效力待定',
    '法定代表人', '授权委托', '证据链', '电子签名', '数据合规', '个人信息保护',
    # 商务条款
    '质保金', '预付款', '进度款', '验收款', '里程碑', '背靠背', '框架协议',
    'SLA', '服务水平协议', '可用性', '响应时间', '恢复时间', '完整性条款',
    '可分割性', '违约责任上限', '赔偿责任上限', '间接损失', '尽职调查',
    '三统一', '开票', '含税价', '不含税价', '增值税', '信用证', '银行承兑',
    # 程序/期限
    '试用期', '解除通知', '催告', '提存机关', '登记', '公示',
]
_TERM_TABLE = sorted(set(_TERM_TABLE), key=len, reverse=True)  # 长词优先匹配

# 数字+单位组合模式(如 30%、5%-10%、3年、20万元、90天)
_NUM_UNIT_RE = re.compile(
    r'\d+(?:\.\d+)?\s*[-~至]?\s*\d*(?:\.\d+)?\s*[%％]'
    r'|\d+(?:\.\d+)?\s*[年月天日周]'
    r'|\d+(?:\.\d+)?\s*[万亿元]'
    r'|\d+(?:\.\d+)?'
)

# 需要从 ground_truth 中提取 3-6 字核心概念的过滤词
_CONCEPT_FILTER = set(
    '的 了 和 是 在 与 及 或 为 对 于 从 到 等 项 条 款 及 其 此 该 之 有 可 应 将 时 后 前 中 内 外 上 下 不 未 已 需 能 会 要 按 依 根据 通过 由于 因为 所以 如果 但 而 且 并 即 如 亦 也 都 只 仅 还 再 更 最 相 同 指 指 是 种 类 型 方式 情况 内容 核心 通常 一般 常见 主要 重要 以下 包括 如下 例如 其中 双方 一方 当事人 合同 条款 约定 规定 义务 权利 责任 承担 履行 支付 交付 提供 收取 享受 主张 请求 可以 应当 需要 必须 不得 禁止 允许 进行 发生 产生 造成 导致 形成 实现 达到 满足 符合 依据 按照 采用 使用 适用 相关 相应 部分 全部 整体 分别 各自 同时 另外 此外 此外 可能 能够 不可 不能 以上 以下 上述 如下'.split()
)


def extract_facts(text: str) -> List[str]:
    """
    从 ground_truth 提取关键事实信号:
    1. 数字+单位组合(百分比/期限/金额)
    2. 法律/商务术语(术语表)
    3. 3-6 字核心概念(去除停用词与噪音)
    返回去重后的信号列表(用于知识覆盖的关键词命中判定)。
    """
    if not text:
        return []
    facts = set()

    # 1. 数字+单位
    for m in _NUM_UNIT_RE.finditer(text):
        tok = m.group().strip()
        if len(tok) >= 2:
            facts.add(tok)

    # 2. 术语表
    for term in _TERM_TABLE:
        if term in text:
            facts.add(term)

    # 3. 3-6 字核心概念(连续中文字段切分)
    for seg in re.findall(r'[\u4e00-\u9fff]{3,6}', text):
        if seg in _CONCEPT_FILTER:
            continue
        if len(seg) >= 3:
            facts.add(seg)

    return sorted(facts)


def entity_hit_rate(facts: List[str], context_text: str) -> float:
    """事实信号在 context 中的出现比例(0~1)。"""
    if not facts:
        return 0.0
    hit = sum(1 for f in facts if f in context_text)
    return hit / len(facts)


def _aligned(doc_title: str, source_document: str) -> bool:
    """source_document(期望来源文档) 与命中文档标题的对齐判断。

    - 期望为空: 视为不可验证(不算命中)
    - 期望非空: 标题包含期望关键词或期望包含标题核心词
    """
    if not source_document or not doc_title:
        return False
    s = source_document.strip()
    t = doc_title.strip()
    if s in t or t in s:
        return True
    # 去除 [评估测试] 前缀后比对核心词
    core_s = s.replace('[评估测试]', '').strip()
    core_t = t.replace('[评估测试]', '').strip()
    if core_s and core_s in core_t or core_t in core_s:
        return True
    return False


# ============================================================
# 覆盖率判定
# ============================================================
# 判定阈值(仅诊断分类用;基于 bge-small 语义相似度实测校准:
# 同类文本 0.6~0.85, 主题相近但无答案 0.45~0.6, 无关 0.3~0.5)
_SEM_STRONG = 0.62   # 语义强覆盖
_SEM_MED = 0.50      # 语义中覆盖
_ENTITY_STRONG = 0.45  # 实体命中率强
_ENTITY_MED = 0.25     # 实体命中率中


def judge_coverage(
    question: str,
    ground_truth: str,
    context_chunks: List[str],
    hit_doc_titles: Optional[List[str]] = None,
    source_document: str = '',
    sim_fn: Optional[Callable[[str, str], float]] = None,
    source_type: str = '',
    kb_coverage: str = '',
) -> Dict[str, Any]:
    """
    判定单题知识覆盖(Sprint 8.9)。

    核心分离(用户要求):
    - Retriever Hit: 检索召回到了内容(evidence.retriever_hit)
    - Knowledge Coverage: 知识库是否存在能支撑答案核心事实的内容(level)

    知识覆盖判定策略:
    - 优先使用数据集标注的 kb_coverage(基于全库 148 chunk 扫描的离线标注,
      综合语义相似度 + 实体命中, 与"检索到了什么"无关, 体现知识库本身的覆盖情况)
    - 标注缺失/unknown 时, 回退在线判定: 以 source_document 是否非空为知识库
      存在性信号, 再结合检索 context 的语义/实体信号综合判断
    - 运行时检索证据(semantic_sim / entity_hit_rate / doc_aligned)始终记录在
      evidence 中, 用于定位"知识库有知识但检索未召回"的 Retriever 问题

    输入(全部复用评估已计算内容, 不重复检索/embedding/LLM):
    - context_chunks: 已检索到的 context chunk 文本列表(复用 retriever 结果)
    - hit_doc_titles: 命中文档标题列表(用于 source_document 对齐诊断)
    - sim_fn: 语义相似度函数(复用评估 sim_fn, 内部缓存向量)

    输出:
    - level: covered / partial / not_covered / unknown(知识库覆盖, 非检索结果)
    - confidence: 判定置信度(0~1)
    - evidence: 运行时信号明细(语义相似度/实体命中/文档对齐/检索命中)
    """
    evidence = {
        'semantic_sim': 0.0,          # max sim(gt, chunk)
        'entity_hit_rate': 0.0,       # 事实信号在 context 的出现比例
        'facts_count': 0,             # gt 提取的事实信号数
        'entity_hit_count': 0,        # 命中事实数
        'matched_facts': [],          # 命中的事实信号
        'missing_facts': [],          # 未命中的事实信号
        'doc_aligned': False,         # source_document 是否命中检索文档(诊断用)
        'retrieved_correct': False,   # 检索是否召回到正确知识(诊断用)
        'context_chunks': len(context_chunks),
        'retriever_hit': len(context_chunks) > 0,
    }

    # ---------- 信号1: 语义相似度(取 context 内最大 chunk 相似度) ----------
    merged_ctx = '\n'.join(context_chunks)
    if sim_fn is not None and context_chunks:
        try:
            max_sim = max(sim_fn(ground_truth, c) for c in context_chunks)
            evidence['semantic_sim'] = round(max_sim, 4)
        except Exception:
            evidence['semantic_sim'] = 0.0

    # ---------- 信号2: 实体/数字/关键词命中率 ----------
    facts = extract_facts(ground_truth)
    evidence['facts_count'] = len(facts)
    matched = [f for f in facts if f in merged_ctx]
    evidence['matched_facts'] = matched
    evidence['missing_facts'] = [f for f in facts if f not in merged_ctx]
    evidence['entity_hit_count'] = len(matched)
    evidence['entity_hit_rate'] = round(
        len(matched) / len(facts), 4) if facts else 0.0

    # ---------- 信号3: 文档来源对齐(诊断用, 不决定知识覆盖) ----------
    if source_document and hit_doc_titles:
        evidence['doc_aligned'] = any(
            _aligned(t, source_document) for t in hit_doc_titles)

    # 检索是否召回到正确知识(覆盖知识 + 检索语义/实体支撑)
    evidence['retrieved_correct'] = bool(
        evidence['doc_aligned'] or (
            evidence['semantic_sim'] >= _SEM_STRONG
            and evidence['entity_hit_rate'] >= _ENTITY_MED
        )
    )

    # ---------- 知识覆盖判定(知识库层面, 与检索结果分离) ----------
    level = 'unknown'
    confidence = 0.0

    kb = (kb_coverage or '').strip().lower()
    if kb in ('covered', 'partial', 'not_covered'):
        # 优先采用离线全库标注(最准确的"知识库是否有知识")
        level = kb
        confidence = 0.95 if kb != 'partial' else 0.8
    elif source_document:
        # 回退: source_document 非空 = 知识库存在对应文档(标注过的期望来源)
        level = 'covered'
        confidence = 0.7
    elif not context_chunks:
        level = 'not_covered'
        confidence = 0.9
    else:
        # 无标注且无文档信号: 用检索语义/实体信号兜底(知识库覆盖最弱证据)
        sem = evidence['semantic_sim']
        ent = evidence['entity_hit_rate']
        if sem >= _SEM_STRONG and ent >= _ENTITY_MED:
            level = 'partial'
            confidence = 0.6
        else:
            level = 'not_covered'
            confidence = 0.7

    return {'level': level, 'confidence': round(confidence, 3),
            'evidence': evidence}


def aggregate_coverage(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    聚合覆盖率统计(明确区分 Retriever Hit 与 Knowledge Coverage)。

    :param samples: per_sample 列表(含 knowledge_coverage 与 evidence)
    :return:
        {
          'total', 'covered', 'partial', 'not_covered', 'unknown',
          'covered_rate', 'partial_rate', 'not_covered_rate',
          'retriever_hit_rate',          # 召回到了内容
          'retrieved_correct_rate',      # 召回到了正确知识(诊断 Retriever 问题)
          'effective_coverage_rate',     # (covered + partial) / total(知识可答率)
          'by_source_type': {source_type: {covered, partial, not_covered, total}},
        }
    """
    n = len(samples)
    if n == 0:
        return {'total': 0}
    cnt = {'covered': 0, 'partial': 0, 'not_covered': 0, 'unknown': 0}
    retriever_hit = 0
    retrieved_correct = 0
    by_type: Dict[str, Dict[str, Any]] = {}

    for s in samples:
        level = s.get('knowledge_coverage') or 'unknown'
        cnt[level] = cnt.get(level, 0) + 1
        # 兼容两种 evidence 字段名(run_rag_eval 中为 coverage_evidence)
        ev = s.get('evidence') or s.get('coverage_evidence') or {}
        if ev.get('retriever_hit'):
            retriever_hit += 1
        if ev.get('retrieved_correct'):
            retrieved_correct += 1
        stype = s.get('source_type') or 'unknown'
        st = by_type.setdefault(stype, {'total': 0, 'covered': 0,
                                        'partial': 0, 'not_covered': 0,
                                        'unknown': 0})
        st['total'] += 1
        st[level] = st.get(level, 0) + 1

    def _rate(k):
        return round(cnt.get(k, 0) / n, 4)

    return {
        'total': n,
        'covered': cnt['covered'],
        'partial': cnt['partial'],
        'not_covered': cnt['not_covered'],
        'unknown': cnt['unknown'],
        'covered_rate': _rate('covered'),
        'partial_rate': _rate('partial'),
        'not_covered_rate': _rate('not_covered'),
        'retriever_hit_rate': round(retriever_hit / n, 4),
        'retrieved_correct_rate': round(retrieved_correct / n, 4),
        'effective_coverage_rate': round(
            (cnt['covered'] + cnt['partial']) / n, 4),
        'by_source_type': by_type,
    }
