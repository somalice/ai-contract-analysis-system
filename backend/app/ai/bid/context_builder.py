"""
Requirement Context Builder (Sprint 7.1 - v0.9.1)

职责:
- Bid Agent 不再直接基于 Requirement 生成投标内容
- 先根据 Requirement 中的技术要求、资格要求、评分标准等关键字段
  自动检索企业知识库(复用 Sprint 4 Retriever),构建结构化 Context
- 将 Context 注入 ProposalContext 供后续 LLM 调用使用

复用:
- Sprint 4: app.ai.rag.retriever.KnowledgeRetriever
  (已通过 knowledge_type 过滤支持 bid/company/case/qualification 四类)

不做:
- 不重新实现 Embedding/VectorStore/FAISS
- 不修改 Sprint 4 Retriever 内部逻辑
- 不新增第二套知识库

输出结构(ctx.rag_context JSON):
{
  "technical": [      // 技术要求对应的企业知识库 Top-K
    {document_id, chunk_id, document_title, page_number,
     score, similarity_score, text, knowledge_type, matched_tech_req}
  ],
  "qualification": [...],  // 资质匹配
  "case": [...],           // 历史案例(招标关键字搜索)
  "company": [...],        // 公司简介/资质总览
  "query_terms": {         // 用于溯源:每个检索槽位的查询词
     "technical": [...],
     "qualification": [...],
     "case": [...]
  }
}
"""
from __future__ import annotations

from typing import Any
import logging
import time

from app.extensions.logger import logger as app_logger


class RequirementContextBuilder:
    """
    Requirement → RAG Context Builder

    使用方式(proposal_service.generate_proposal 流程中):
        builder = RequirementContextBuilder(retriever)
        rag_context = builder.build(requirements, company_profile)
        ctx.rag_context = rag_context
    """

    # ----- 知识类型映射 -----
    # 检索槽位 → knowledge_type 白名单(复用 Sprint 4 knowledge_type 过滤)
    SLOT_TYPES = {
        'technical': ('case', 'bid', 'company'),   # 技术方案:参考历史项目/投标/公司技术栈
        'qualification': ('qualification', 'company'),  # 资质:资质文档/公司资质
        'case': ('case', 'bid'),                   # 案例:历史项目/历史投标
        'company': ('company',),                   # 公司总览:公司文档
    }

    # 每个槽位 Top-K
    SLOT_TOP_K = {
        'technical': 5,
        'qualification': 4,
        'case': 4,
        'company': 3,
    }

    def __init__(self, retriever: Any):
        """
        :param retriever: Sprint 4 KnowledgeRetriever 实例
                          (必须具备 .search(query, top_k, knowledge_types) 接口)
        """
        self.retriever = retriever
        self._verify_retriever()

    def _verify_retriever(self):
        """确保 retriever 具备预期接口(软校验,失败不抛错,仅 warn)"""
        if not hasattr(self.retriever, 'search'):
            app_logger.warning(
                '[RequirementContextBuilder] retriever 无 .search 接口,'
                ' RAG Context 将构建为空;请确认 Sprint 4 Retriever 是否正确注入'
            )

    # ============================================================
    # 主入口
    # ============================================================
    def build(self, requirements: dict, company_profile: dict | None = None) -> dict:
        """
        根据 Requirement 自动构建 Context

        :param requirements: BidRequirement.requirement_data(15 字段 dict)
        :param company_profile: 公司简介 dict(兜底,无 RAG 时可直接塞进去)
        :return: rag_context dict
        """
        t0 = time.time()
        requirements = requirements or {}
        company_profile = company_profile or {}

        result: dict = {
            'technical': [],
            'qualification': [],
            'case': [],
            'company': [],
            'query_terms': {
                'technical': [],
                'qualification': [],
                'case': [],
                'company': [],
            },
            'stats': {
                'retrieved_count': 0,
                'slots_filled': 0,
                'duration_ms': 0,
            },
        }

        # ---- 生成各槽位的查询词 ----
        tech_reqs = _normalize_list(requirements.get('technical_requirements'))
        qual_reqs = _normalize_list(requirements.get('qualification_requirements'))
        scoring = _normalize_list(requirements.get('scoring_criteria'))
        project_name = str(requirements.get('project_name') or '')
        tender_org = str(requirements.get('tender_org') or '')
        project_location = str(requirements.get('project_location') or '')

        # 技术查询:取前 3 条 + 评分标准前 2 条
        tech_queries = _merge_queries(
            [_req_to_query(x) for x in tech_reqs[:3]]
            + [_req_to_query(x) for x in scoring[:2]]
        )
        # 资质查询:取所有资质要求
        qual_queries = _merge_queries([_req_to_query(x) for x in qual_reqs])
        # 案例查询:项目名称 + 招标单位 + 地点 + 技术要求关键字
        case_queries = _merge_queries(
            [project_name, tender_org, project_location]
            + [_req_to_query(x) for x in tech_reqs[:2]]
        )
        # 公司查询:固定"公司简介/资质/案例"
        company_queries = ['公司简介 企业资质 技术能力 业务范围']

        result['query_terms']['technical'] = tech_queries
        result['query_terms']['qualification'] = qual_queries
        result['query_terms']['case'] = case_queries
        result['query_terms']['company'] = company_queries

        # ---- 依次检索 4 个槽位 ----
        filled_slots = 0
        total_docs = 0

        for slot, queries in (
            ('technical', tech_queries),
            ('qualification', qual_queries),
            ('case', case_queries),
            ('company', company_queries),
        ):
            slot_docs = self._slot_search(slot, queries)
            if slot_docs:
                filled_slots += 1
                total_docs += len(slot_docs)
            result[slot] = slot_docs

        # ---- 兜底:无 RAG 结果时,直接把 company_profile 挂到 company 槽 ----
        if not result['company'] and company_profile:
            result['company'].append({
                'document_id': 'company_profile',
                'chunk_id': 'company_profile_01',
                'document_title': '企业资料(非知识库来源)',
                'page_number': 0,
                'score': 0.0,
                'similarity_score': 0.0,
                'text': f"公司名称:{company_profile.get('name','')} | "
                        f"主营业务:{company_profile.get('business','')} | "
                        f"资质:{company_profile.get('qualifications','')} | "
                        f"案例:{company_profile.get('cases','')}",
                'knowledge_type': 'company_profile_inline',
                'matched_tech_req': None,
            })
            filled_slots += 1
            total_docs += 1

        result['stats'] = {
            'retrieved_count': total_docs,
            'slots_filled': filled_slots,
            'duration_ms': int((time.time() - t0) * 1000),
        }

        app_logger.info(
            '[RequirementContextBuilder] build ok: slots=%d/4, docs=%d, duration=%dms',
            filled_slots, total_docs, result['stats']['duration_ms']
        )
        return result

    # ============================================================
    # 槽位检索辅助
    # ============================================================
    def _slot_search(self, slot: str, queries: list[str]) -> list[dict]:
        """
        单个槽位检索
        - 若 retriever 不可用:返回空(不影响主流程)
        - 每条 query 调用一次 .search,按相似度排序合并,截断 TOP_K
        - 文档结构映射为 Sprint 5 统一 4 字段(+ 扩展字段)
        """
        if not hasattr(self.retriever, 'search') or not queries:
            return []

        k = self.SLOT_TOP_K.get(slot, 5)
        ktypes = self.SLOT_TYPES.get(slot) or ()

        seen: set[str] = set()
        merged: list[dict] = []
        # 所有 query 用同一个 k 检索,再合并去重取前 k
        per_query_k = min(k, 5)
        for q in queries:
            try:
                if ktypes:
                    docs = self.retriever.search(q, top_k=per_query_k,
                                                 knowledge_types=list(ktypes))
                else:
                    docs = self.retriever.search(q, top_k=per_query_k)
            except Exception as e:
                app_logger.warning('[RequirementContextBuilder] slot=%s query=%s 检索异常:%s',
                               slot, q, e)
                continue

            if not docs:
                continue
            for d in _ensure_list(docs):
                doc_id = str(_dict_get(d, 'document_id') or _dict_get(d, 'id') or '')
                chunk_id = str(_dict_get(d, 'chunk_id') or '')
                key = f"{doc_id}::{chunk_id}"
                if key in seen:
                    continue
                seen.add(key)
                score = _dict_get(d, 'score') or _dict_get(d, 'similarity_score') or 0.0
                try:
                    score = float(score)
                except (TypeError, ValueError):
                    score = 0.0
                merged.append({
                    'document_id': doc_id or None,
                    'chunk_id': chunk_id or None,
                    'document_title': _dict_get(d, 'document_title') or _dict_get(d, 'title') or '',
                    'page_number': _dict_get(d, 'page_number') or 0,
                    'score': score,
                    # ----- 统一 4 字段(Bid References 要求,与 Sprint 5 对齐) -----
                    'similarity_score': score,
                    'text': _dict_get(d, 'text') or _dict_get(d, 'content') or '',
                    'knowledge_type': _dict_get(d, 'knowledge_type') or '',
                    'matched_query': q,
                })

        # 按相似度降序截断
        merged.sort(key=lambda x: x['similarity_score'], reverse=True)
        return merged[:k]


# ================================================================
# 工具函数(独立,无副作用,便于单测)
# ================================================================
def _normalize_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [x.strip() for x in v.splitlines() if x.strip()]
    return [v]


def _req_to_query(req: Any) -> str:
    """把要求条目(可以是 str/dict)转成 query 字符串"""
    if not req:
        return ''
    if isinstance(req, str):
        return req.strip()
    if isinstance(req, dict):
        parts = []
        for key in ('item', 'content', 'description', 'name', 'requirement', 'criterion'):
            if req.get(key):
                parts.append(str(req[key]).strip())
        return ' '.join(parts).strip()
    return str(req).strip()


def _merge_queries(candidates: list[str]) -> list[str]:
    """
    合并查询:
    - 去重 + 过滤空
    - 长度 > 10 的独立保留
    - 长度 <= 10 的两两拼接,避免 RAG 无意义短 query
    - 最多返回 3 条
    """
    clean = [s for s in dict.fromkeys(candidates) if s and len(s) >= 2]
    if not clean:
        return []
    long_queries = [s for s in clean if len(s) >= 10][:3]
    short_queries = [s for s in clean if len(s) < 10]
    merged = list(long_queries)
    if short_queries and len(merged) < 3:
        merged.append(' '.join(short_queries[:3]))
    return merged[:3]


def _ensure_list(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    # 有些 retriever 返回 tuple/生成器
    try:
        return list(v)
    except Exception:
        return []


def _dict_get(obj, key: str, default=None):
    """dict.get() 的健壮版,兼容非 dict"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return getattr(obj, key, default)
    except Exception:
        return default
