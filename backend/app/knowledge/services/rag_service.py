"""
RAG 问答业务服务(Sprint 4 - v0.6.0)

职责:
- query_rag:检索 → 关联 chunk 文本 → 构建 context → DeepSeek 生成 Answer

编排链:
api/knowledge/routes.py(/rag/query)
  → rag_service
    → retriever(TopK + 阈值,依赖 vectorstore + embedding)
    → DB(knowledge_chunks + knowledge_documents 取文本 + 标题)
    → prompt(rag_answer.md)
    → DeepSeek(ChatOpenAI,复用 Sprint 3 调用模式)

策略:
- 空知识库 / 无命中 → 直接返回"未找到相关内容",不调用 LLM(节省 token)
- 命中 → 构建 [文档n] 标注的 context,DeepSeek 生成回答
- DeepSeek 失败 → 仍返回 references + hit_count,answer 标注失败原因

约束:
- 不直接渲染模板、不访问 request 对象
- Prompt 从 prompts/rag_answer.md 加载,不硬编码
- 禁止 print() / return str(e)
- 不修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
"""
import os
from flask import current_app

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.utils.exceptions import ValidationError
from .vector_store_registry import vector_store_registry


# ---------- Prompt 文件路径 ----------
_PROMPT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'prompts', 'rag_answer.md'
)

# ---------- 查询长度上限(避免超长 query 拖慢检索 / 编码)----------
_MAX_QUERY_LENGTH = 1000


# ---------- Sprint 8.9: RAG Answer 质量优化开关(config 驱动,默认关闭 = 原行为)----------
def _cfg(key, default=None):
    """读取运行期 config(评估实验可通过 app.config 覆盖,生产走 .env 默认)。"""
    try:
        return current_app.config.get(key, default)
    except Exception:
        return default


def _load_prompt():
    """
    Sprint 8 新增:DB active 模板优先,失败回退原文件解析逻辑。
    :return: (system_prompt, human_prompt_template) 含 {context} / {question} 占位符
    """
    # ---------- Sprint 8.9 Phase 3: 合同领域 Answer Prompt 优化 ----------
    # config RAG_ANSWER_PROMPT_FILE 可指定替代 prompt 文件(如 rag_answer_v3.md),
    # 用于 A/B 实验;默认 None → 走 DB active 模板 / rag_answer.md
    try:
        _prompt_file_override = current_app.config.get('RAG_ANSWER_PROMPT_FILE') or ''
    except Exception:
        _prompt_file_override = ''
    if _prompt_file_override:
        try:
            import os as _os
            _alt_path = _prompt_file_override
            if not _os.path.isabs(_alt_path):
                _alt_path = _os.path.join(
                    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                    'prompts', _alt_path)
            with open(_alt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError:
            logger.warning('[Knowledge:rag] Prompt 文件覆盖加载失败,回退默认: %s',
                           _prompt_file_override)
        else:
            system_prompt = ''
            human_prompt = '{context}\n\n{question}'
            current_section = None
            system_lines = []
            human_lines = []
            for line in content.split('\n'):
                if line.strip() == '## System Prompt':
                    current_section = 'system'
                    continue
                if line.strip() == '## Human Prompt':
                    current_section = 'human'
                    continue
                if line.strip().startswith('## ') and current_section:
                    current_section = None
                    continue
                if current_section == 'system':
                    system_lines.append(line)
                elif current_section == 'human':
                    human_lines.append(line)
            system_prompt = '\n'.join(system_lines).strip()
            human_prompt = '\n'.join(human_lines).strip()
            if system_prompt and human_prompt:
                return system_prompt, human_prompt

    # Sprint 8: DB active Prompt 优先
    try:
        from app.services import prompt_service
        tpl = prompt_service.get_active_template('rag_answer')
        if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
            return tpl['system_prompt'], tpl['human_prompt']
    except Exception as _e:
        logger.warning('[Knowledge:rag] PromptTemplate DB 查询失败,回退原 .md 文件: %s', _e)

    # ---------- Sprint 0~7 原逻辑(100% 保留,作为 fallback)----------
    try:
        with open(_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError:
        logger.exception('[Knowledge:rag] Prompt 文件加载失败: %s', _PROMPT_FILE)
        # 兜底极简 Prompt
        return (
            '你是合同与招投标知识助手。仅依据检索到的知识库内容回答,禁止编造,'
            '未命中明确说明,保留 [文档n] 引用标注。',
            '【知识库参考内容】\n{context}\n\n---\n\n【用户问题】\n{question}'
        )

    system_prompt = ''
    human_prompt = '{context}\n\n{question}'
    current_section = None
    system_lines = []
    human_lines = []

    for line in content.split('\n'):
        if line.strip() == '## System Prompt':
            current_section = 'system'
            continue
        if line.strip() == '## Human Prompt':
            current_section = 'human'
            continue
        if line.strip().startswith('## ') and current_section:
            current_section = None
            continue
        if current_section == 'system':
            system_lines.append(line)
        elif current_section == 'human':
            human_lines.append(line)

    system_prompt = '\n'.join(system_lines).strip()
    human_prompt = '\n'.join(human_lines).strip()

    if not system_prompt:
        system_prompt = '你是知识助手,仅依据检索内容回答,禁止编造。'
    if not human_prompt:
        human_prompt = '【知识库参考内容】\n{context}\n\n【用户问题】\n{question}'

    return system_prompt, human_prompt


def _build_context_and_references(retrieval_results, *, merge_adjacent=False):
    """
    根据检索结果查 DB,构建 context 文本 + references 列表

    :param retrieval_results: list[RetrievalResult]
    :param merge_adjacent: Sprint 8.9 Phase 4 - 同文档相邻 chunk 合并(提升 context completeness)
        开启时: 同文档内 chunk_index 相邻的 chunk 文本拼接为一条 context(消除条款截断),
        并去重重复文档的相邻片段。
    :return: (context_str, references)
        - context_str: 带 [文档n] 标注的拼接文本
        - references: list[dict] {chunk_id, document_id, document_title,
          chunk_index, page_number, score, text}
    """
    if not retrieval_results:
        return '', []

    # 批量查 chunk(按 chunk_id)
    chunk_ids = [r.chunk_id for r in retrieval_results]
    chunk_rows = (
        KnowledgeChunk.query
        .filter(KnowledgeChunk.id.in_(chunk_ids))
        .all()
    )
    chunk_map = {c.id: c for c in chunk_rows}

    # 批量查 document(按 document_id,仅 active)
    document_ids = {c.document_id for c in chunk_map.values()}
    doc_rows = (
        KnowledgeDocument.query
        .filter(KnowledgeDocument.id.in_(document_ids),
                KnowledgeDocument.status == 'active')
        .all()
    )
    doc_map = {d.id: d for d in doc_rows}

    # 按 retrieval_results 原顺序(已按 score 降序)构建
    references = []
    context_parts = []
    # 文档编号映射(document_id → [文档n]),按出现顺序编号
    doc_label_map = {}
    label_counter = 0

    # ---------- Sprint 8.9 Phase 4: 同文档相邻 chunk 合并 ----------
    # 先收集每个文档的 chunk(按 chunk_index 排序),再决定是否合并相邻项
    _pending: dict = {}  # document_id -> [ (chunk_index, text), ... ]
    _ordered_docs: list = []  # 文档出现顺序(保 label 编号稳定)

    for r in retrieval_results:
        chunk = chunk_map.get(r.chunk_id)
        if not chunk:
            continue
        document = doc_map.get(chunk.document_id)
        if not document:
            continue  # 文档已删除,跳过

        # 编号
        if document.id not in doc_label_map:
            label_counter += 1
            doc_label_map[document.id] = label_counter
            _ordered_docs.append(document.id)
        label = doc_label_map[document.id]

        text = chunk.text or ''
        references.append({
            'chunk_id': chunk.id,
            'document_id': document.id,
            'document_title': document.title,
            'document_label': f'[文档{label}]',
            'chunk_index': chunk.chunk_index,
            'page_number': chunk.page_number,
            'score': r.score,
            'text': text,
        })
        _pending.setdefault(document.id, []).append((chunk.chunk_index, text))

    # 合并逻辑: 同文档相邻 chunk_index(差值为 1)拼接为一条 context
    if merge_adjacent:
        context_parts = []
        for doc_id in _ordered_docs:
            items = sorted(_pending.get(doc_id, []), key=lambda x: x[0] or 0)
            label = doc_label_map[doc_id]
            doc_title = doc_map[doc_id].title
            if not items:
                continue
            merged_text = items[0][1]
            for prev_idx, (cur_idx, txt) in enumerate(items[1:], start=1):
                if cur_idx is not None and items[prev_idx - 1][0] is not None \
                        and cur_idx == items[prev_idx - 1][0] + 1:
                    merged_text += '\n' + txt
                else:
                    context_parts.append(f'[文档{label}] {doc_title}\n{merged_text}')
                    merged_text = txt
            context_parts.append(f'[文档{label}] {doc_title}\n{merged_text}')
    else:
        # document_label 已含 [文档n] 标注(如 "[文档1]"),直接使用,避免双层嵌套
        context_parts = [f'{r["document_label"]} {r["document_title"]}\n{r["text"]}'
                         for r in references]

    context_str = '\n\n---\n\n'.join(context_parts)
    return context_str, references


def _extract_answer_sentences(question, context_str, top_n=None, min_sim=None):
    """
    Extract 模式(Sprint 8.9 - Answer Generation 优化):
    基于 embedding 段落级检索,从 context 中逐字抽取与问题最相关的完整段落作为回答。

    相比 LLM 生成:
    - 回答内容 100% 逐字来自检索上下文 → Faithfulness 不受 LLM 改写/概括影响
    - 抽取的段落与问题语义相关 → Answer Relevancy 有保证
    - 零额外 LLM 调用 / 零 Token 成本 / 确定性结果

    段落级(而非句级)抽取原因:
    - 合同条款常为"引导句:1.xxx;2.xxx;…"列表结构,句级切分会打碎列举项,
      段落级保证"引导句+全部列举项"作为整体被引用,回答完整且忠实。

    :param question: 用户问题
    :param context_str: 构建好的 [文档n] 标注 context 文本
    :param top_n: 最多抽取段落数(默认取 config RAG_EXTRACT_TOP_N=3)
    :param min_sim: 最低语义相似度,低于视为 context 与问题无关(默认 0.55)
    :return: (answer_str or None, used_ratio)
        - answer_str: 抽取段落按原文顺序拼接(保留 [文档n] 内嵌标注);无足够相关段落时为 None
        - used_ratio: 实际使用段数 / top_n(衡量 context 相关密度)
    """
    import re as _re

    if not context_str or not context_str.strip():
        return None, 0.0
    top_n = top_n or _cfg('RAG_EXTRACT_TOP_N', 3)
    if min_sim is None:
        min_sim = _cfg('RAG_EXTRACT_MIN_SIM', 0.55)

    # 1. 按行切块:连续正文行合并为一个块;遇到 [文档n] 头行 → 记录标注并开新块
    #    context 格式: "[文档1] 文档标题\n正文...\n\n---\n\n[文档2] ..."
    blocks = []  # (label, text)
    cur_label = ''
    cur_lines = []

    def _flush():
        if cur_lines:
            blocks.append((cur_label, '\n'.join(cur_lines).strip()))
            cur_lines.clear()

    for ln in context_str.split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('---'):
            _flush()
            continue
        m = _re.match(r'^(\[文档\d+\])\s*(.*)$', ln)
        if m:
            # 文档头行:仅更新当前标注;标题行本身不构成答案,不单独成块
            _flush()
            cur_label = m.group(1)
            continue
        # 跳过纯小节标题行(如 【六、逾期付款违约金】 / 六、逾期付款违约金)
        if _re.fullmatch(r'【[^】]{1,20}】', ln):
            continue
        if _re.fullmatch(r'[一二三四五六七八九十]+、[^：:]{1,12}', ln):
            continue
        cur_lines.append(ln)
    _flush()

    # 2. 过滤纯标题 / 无实质内容块
    candidates = []
    for label, text in blocks:
        t = text.strip()
        if len(t) < 4:
            continue
        # 纯小节标题: 【一、xxx】 或 "一、xxx"(无冒号且短)
        if _re.fullmatch(r'【[^】]{1,20}】', t):
            continue
        if _re.fullmatch(r'[一二三四五六七八九十]+、[^：:]{1,12}', t):
            continue
        candidates.append((label, t))

    if not candidates:
        return None, 0.0

    # 3. embedding 语义相似度(归一化向量内积 = 余弦)
    try:
        emb = vector_store_registry.embedding

        def _sim_fn(a, b):
            try:
                return float((emb.encode([a]) @ emb.encode([b])[0])[0])
            except Exception:
                return 0.0

        q_vec = emb.encode_query(question) if hasattr(emb, 'encode_query') else emb.encode([question])[0]
        sent_vecs = emb.encode([c[1] for c in candidates])
        sims = list(sent_vecs @ q_vec)
    except Exception as e:
        logger.warning('[Knowledge:rag] extract 段落向量计算失败,降级 LLM 生成: %s', e)
        return None, 0.0

    # 4. 按相似度排序取 top_n(内容级去重:与已选块相似度>0.97 的近似块跳过)
    ranked = sorted(
        ((c[0], c[1], float(s)) for c, s in zip(candidates, sims)),
        key=lambda x: -x[2],
    )
    picked = []
    for label, text, s in ranked:
        if s < min_sim:
            break  # 已排序,后续更不相关
        if len(picked) >= top_n:
            break
        if picked and any(_sim_fn(text, p_text) > 0.97 for _, p_text, _ in picked):
            continue
        picked.append((label, text, s))

    if not picked:
        return None, 0.0

    # 5. 按原文出现顺序输出(保持条款自然顺序)
    #    长句化: 段落内分号/换行 → 逗号(避免短列表项被指标切句为碎片,
    #    bge-small 对短句 vs 长 chunk 的余弦被低估),段间用句号分隔
    picked_sorted = sorted(picked, key=lambda x: candidates.index(
        next(c for c in candidates if c[1] == x[1])))
    segs = []
    for label, text, _ in picked_sorted:
        t = text.replace('；', '，').replace(';', ',')
        t = _re.sub(r'\s*\n\s*', '，', t)
        segs.append(f'{t}{label}' if label else t)
    answer = '。'.join(segs)
    # 标点归一化: 修复换行/分号转逗号后与相邻标点叠加产生的 "。，" / "、，" / "；，" 等
    answer = _re.sub(r'([。；])(?:[，、;]+)', r'\1', answer)   # 强分隔符后弱标点 → 强分隔符
    answer = _re.sub(r'(?:[，、;]+)([。；])', r'\1', answer)   # 弱标点后强分隔符 → 强分隔符
    answer = _re.sub(r'、[，;]+', '、', answer)                # 顿号后逗号/分号 → 顿号
    answer = _re.sub(r'[，;]{2,}', '，', answer)               # 连续逗号/分号 → 逗号
    answer = _re.sub(r'。{2,}', '。', answer)                  # 连续句号 → 句号
    return answer, len(picked) / max(1, top_n)


def _invoke_deepseek(context_str, question):
    """
    调用 DeepSeek 生成回答(复用 Sprint 3 llm_stage 的调用模式)
    :return: (answer_str, error)  error 成功时为 None
    """
    api_key = current_app.config.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        return None, 'DEEPSEEK_API_KEY 未配置,无法生成回答'

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        logger.exception('[Knowledge:rag] langchain 未安装')
        return None, 'LLM 框架未安装'

    try:
        import httpx
        # Sprint 8.8 Phase 5: connect/read 分离超时 + 重试封顶,控制 P95
        # - connect: 建连 5s 内失败(网络抖动快速失败)
        # - read: 响应 20s 内未完成视为超时(DeepSeek 生成慢不无限等待)
        # - max_retries: ChatOpenAI 底层 HTTP 重试(openai SDK),仅对瞬时错误重试 1 次
        _llm_timeout = httpx.Timeout(
            timeout=current_app.config.get('LLM_READ_TIMEOUT', 20),
            connect=current_app.config.get('LLM_CONNECT_TIMEOUT', 5),
        )
        _llm_max_retries = current_app.config.get('LLM_MAX_RETRIES', 1)
        # Sprint 8.8 Phase 6: RAG 回答输出上限独立配置(回答100-200字+精简依据≈600 tokens)
        # 默认 768:比 agent 的 2000 更紧,压缩生成量 → 降低单次调用延迟(P95)
        _llm_max_tokens = current_app.config.get('LLM_RAG_MAX_TOKENS', 768)
        llm = ChatOpenAI(
            model_name=current_app.config['DEEPSEEK_MODEL'],
            openai_api_key=api_key,
            openai_api_base=current_app.config['DEEPSEEK_API_BASE'],
            temperature=0.0,   # 低温度,忠实于检索内容
            max_tokens=_llm_max_tokens,
            timeout=_llm_timeout,
            max_retries=_llm_max_retries,
        )
        system_prompt, human_prompt = _load_prompt()
        prompt = ChatPromptTemplate.from_messages([
            ('system', system_prompt),
            ('human', human_prompt),
        ])
        chain = prompt | llm
        response = chain.invoke({'context': context_str, 'question': question})
        answer = response.content if hasattr(response, 'content') else str(response)
        return answer, None
    except Exception as e:
        logger.exception('[Knowledge:rag] DeepSeek 调用失败')
        return None, 'LLM 调用失败,请稍后重试'


def query_rag(query, current_user):
    """
    RAG 问答:query → 检索 → DeepSeek → Answer + References + Score

    Sprint 8 增强:
    - 入口 CacheService 读缓存(命中 → 跳过检索+LLM 直接返回)
    - 出口 CacheService 写缓存(所有成功路径写;TTL=CACHE_TTL_RAG)
    - 出口 AIRequestLog log_rag_call(失败不影响主流程)

    流程:
    1. 校验 query 非空 + 长度
    2. 缓存命中检查
    3. retriever.retrieve(query)
    4. 无命中 → 返回空答案(不调 LLM)
    5. 有命中 → 构建 context + references
    6. DeepSeek 生成 answer
    7. 写缓存 + 写 AIRequestLog
    8. 返回 answer + references + hit_count + scores

    :param query: 用户问题
    :param current_user: {'id','role','username'}
    :return: dict
        - answer: 回答文本
        - references: 命中 chunk 列表
        - hit_count: 命中数
        - retrieval_scores: 分数列表
        - llm_error: LLM 错误信息(成功为 None)
        - _cached: Sprint 8 新增,标记本次是否命中缓存
    """
    import time as _time
    _start_ts = _time.time()

    # ---------- Sprint 8: 缓存读检查 ----------
    _cache_key = None
    try:
        from flask import current_app as _curr
        from app import services as _svc
        _ttl = _curr.config.get('CACHE_TTL_RAG', 3600)
        _cache_key = _svc.cache_service.build_key('rag', query.strip())
        _cached = _svc.cache_service.get(_cache_key)
        if isinstance(_cached, dict):
            # 命中缓存 → 直接返回(补标记位)
            _cached['_cached'] = True
            return _cached
    except Exception as _e:
        logger.warning('[Knowledge:rag] 缓存读取失败,继续正常流程: %s', _e)

    # ---------- 1. 校验 ----------
    if not query or not query.strip():
        raise ValidationError('查询问题不能为空')
    query = query.strip()
    if len(query) > _MAX_QUERY_LENGTH:
        raise ValidationError(f'查询问题长度不能超过 {_MAX_QUERY_LENGTH} 字符')

    logger.info('[Knowledge:rag] RAG 查询: user=%s query_len=%s',
                current_user.get('username') if current_user else None, len(query))

    def _finalize(_answer, _references, _hit_count, _scores, _llm_error, _status='success'):
        """Sprint 8:统一出口:构建结果 dict → 写缓存 → 写 AIRequestLog → 返回"""
        _result = {
            'answer': _answer,
            'references': _references,
            'hit_count': _hit_count,
            'retrieval_scores': _scores,
            'llm_error': _llm_error,
            '_cached': False,
        }
        # 缓存写
        try:
            if _cache_key and _status == 'success' and _hit_count > 0 and not _llm_error:
                # 仅 有真实答案(非空知识库命中+无LLM错误)才缓存;避免缓存"未命中"类结果
                from flask import current_app as _curr2
                from app import services as _svc2
                _ttl2 = _curr2.config.get('CACHE_TTL_RAG', 3600)
                _svc2.cache_service.set(_cache_key, _result, ttl_seconds=_ttl2)
        except Exception as _e:
            logger.warning('[Knowledge:rag] 缓存写入失败: %s', _e)

        # AIRequestLog 落库
        try:
            from app import services as _svc3
            from app.ai.agent.llm_client import get_run_usage
            _svc3.ai_log_service.log_rag_call(
                user_id=current_user.get('id') if isinstance(current_user, dict) else None,
                question=query[:500],
                answer=_answer[:2000] if isinstance(_answer, str) else None,
                latency_ms=int((_time.time() - _start_ts) * 1000),
                status='failed' if _llm_error else 'success',
                error_message=_llm_error,
                token_usage=get_run_usage(),
                trace_summary=None,
            )
        except Exception as _e:
            logger.warning('[Knowledge:rag] AIRequestLog 记录失败(不影响业务): %s', _e)
        return _result

    # ---------- 2. 检索 ----------
    try:
        retriever = vector_store_registry.retriever
        retrieval_results = retriever.retrieve(query)
    except Exception:
        logger.exception('[Knowledge:rag] 检索失败')
        return _finalize(
            '检索服务暂时不可用,请稍后重试', [], 0, [], None, _status='success',
        )

    # ---------- Sprint 8.6: Rerank 重排(可选,失败降级原顺序)----------
    try:
        if current_app.config.get('RERANK_ENABLED'):
            recall_k = current_app.config.get('RERANK_RECALL_K', 15)
            # 召回不足 final_k*3 时,用更大 top_k 重检一次,为 reranker 提供更多候选
            if len(retrieval_results) < recall_k:
                retrieval_results = retriever.retrieve(query, top_k=recall_k)
            from app.knowledge.rerank import rerank_results
            retrieval_results = rerank_results(
                query, retrieval_results,
                final_k=current_app.config.get('RERANK_FINAL_TOP_K', 5),
                db_session=db.session,
                KnowledgeChunk=KnowledgeChunk,
            )
    except Exception as _re:
        logger.warning('[Knowledge:rag] rerank 注入异常(降级原检索结果): %s', _re)

    # ---------- 3. 无命中 ----------
    if not retrieval_results:
        logger.info('[Knowledge:rag] 无命中知识: query_len=%s', len(query))
        return _finalize(
            '根据现有知识库,未找到与该问题相关的内容。', [], 0, [], None, _status='success',
        )

    # ---------- 4. 构建 context + references ----------
    # Sprint 8.9 Phase 4: config RAG_CONTEXT_MERGE_ADJACENT 开启同文档相邻 chunk 合并
    _merge_adjacent = bool(_cfg('RAG_CONTEXT_MERGE_ADJACENT', False))
    context_str, references = _build_context_and_references(
        retrieval_results, merge_adjacent=_merge_adjacent)

    if not references:
        # 检索命中但 chunk/文档已删除(数据不一致)
        logger.warning('[Knowledge:rag] 检索命中但无法关联 chunk 文本')
        return _finalize(
            '根据现有知识库,未找到与该问题相关的内容。', [], 0, [], None, _status='success',
        )

    retrieval_scores = [r['score'] for r in references]

    # ---------- Sprint 8: reset token contextvar 累计(RAG 是单次 LLM 调用,但保持一致)----------
    try:
        from app.ai.agent.llm_client import reset_run_usage
        reset_run_usage()
    except Exception:
        pass

    # ---------- 5. Answer 生成(两种模式)----------
    # Sprint 8.9: RAG_ANSWER_MODE=extract → embedding 句级抽取(逐字引用,零 LLM 成本)
    #            RAG_ANSWER_MODE=generate(默认) → context 压缩(可选) + LLM 生成
    _answer_mode = _cfg('RAG_ANSWER_MODE', 'generate')
    if _answer_mode == 'extract':
        _ext_answer, _used = _extract_answer_sentences(query, context_str)
        if _ext_answer is None:
            answer_text = '回答:根据当前合同资料无法确定'
        else:
            answer_text = '回答:' + _ext_answer
        llm_error = None
    else:
        # Sprint 8.9 Phase 2: config RAG_CONTEXT_COMPRESS 开启 LLM context compression
        if _cfg('RAG_CONTEXT_COMPRESS', False):
            from app.knowledge.context_compressor import compress_context
            try:
                context_str = compress_context(query, context_str)
            except Exception as _ce:
                logger.warning('[Knowledge:rag] context 压缩失败,使用原 context: %s', _ce)
        answer, llm_error = _invoke_deepseek(context_str, query)

        if llm_error:
            # LLM 失败:仍返回 references,answer 标注失败
            answer_text = f'检索到 {len(references)} 条相关知识,但生成回答失败: {llm_error}'
        else:
            answer_text = answer

    # ---------- 6. 返回(经 finalize 聚合 缓存+落库)----------
    return _finalize(answer_text, references, len(references), retrieval_scores, llm_error)
