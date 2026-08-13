"""Sprint 8.10 - RAG Evaluation Embedding Calibration

目的:
    验证当前评估指标使用的 sim_fn embedding(BAAI/bge-small-zh-v1.5)是否造成
    Faithfulness / Answer Relevancy 的系统性低估,并对比 bge-large-zh-v1.5 / bge-m3。

唯一变量:
    evaluation 阶段 sim_fn 使用的 embedding 模型。
    question / ground_truth / answer / context_chunks / metric formula 全部固定
    (来自 Sprint 8.9 production regression 确定性捕获,scripts/eval_embedding_calibration_data.json)。

严格禁止(本脚本不执行):
    - 重新调用 query_rag() / Retriever / Rerank / LLM
    - 修改生产 rag_service / retriever / rerank / extract 参数 / dataset / gt / 阈值

生产安全:
    - 生产 embedding 始终为 BAAI/bge-small-zh-v1.5(vector_store_registry 不变)
    - 三个实验 embedding 均独立实例化(SentenceTransformerEmbedding 懒加载本地模型),
      独立持久化缓存 scripts/evaluation_embedding_cache/<model_key>/,cache key 含 model_name + text_hash,
      不会污染生产 embedding cache。
"""
from __future__ import annotations

import json
import math
import re
import statistics as st
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / '.env')

# 三个实验模型(Sprint 8.10 任务书)
MODELS = {
    'bge-small': 'BAAI/bge-small-zh-v1.5',
    'bge-large': 'BAAI/bge-large-zh-v1.5',
    'bge-m3': 'BAAI/bge-m3',
}
# 归档基线(Sprint 8.9 Production Regression)
ARCHIVED = {'faithfulness': 0.8382, 'answer_relevancy': 0.7373,
            'context_precision': 0.8117, 'context_recall': 0.8233}
# 独立缓存目录(不污染生产 embedding cache)
CACHE_ROOT = REPO_ROOT / 'scripts' / 'evaluation_embedding_cache'
DATA_PATH = REPO_ROOT / 'scripts' / 'eval_embedding_calibration_data.json'
OUT_PATH = REPO_ROOT / 'scripts' / 'eval_embedding_calibration.json'

TARGETS = {'faithfulness': 0.85, 'answer_relevancy': 0.85,
           'context_precision': 0.80, 'context_recall': 0.80}


# ============================================================
# 工具
# ============================================================
def _split_sents(text: str) -> list:
    """切句(与 rag_metrics.faithfulness 同口径)。"""
    sents = [s.strip() for s in re.split(r'[。；;\n!?？!]', text)
             if s.strip() and len(s.strip()) >= 2]
    return sents


def _spearman(xs: list, ys: list) -> float:
    """Spearman 秩相关系数(自行实现,不依赖 scipy)。"""
    n = len(xs)
    if n < 3:
        return 0.0

    def _rank(vals):
        idx = sorted(range(n), key=lambda i: vals[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[idx[j + 1]] == vals[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[idx[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _dist_stats(vals: list) -> dict:
    if not vals:
        return {'mean': 0.0, 'median': 0.0, 'min': 0.0, 'max': 0.0, 'p25': 0.0, 'p75': 0.0}
    s = sorted(vals)
    n = len(s)

    def _pct(p):
        k = (n - 1) * p
        f, c = math.floor(k), math.ceil(k)
        if f == c:
            return s[int(k)]
        return s[f] * (c - k) + s[c] * (k - f)

    return {'mean': round(st.mean(s), 4), 'median': round(st.median(s), 4),
            'min': round(s[0], 4), 'max': round(s[-1], 4),
            'p25': round(_pct(0.25), 4), 'p75': round(_pct(0.75), 4)}


def _mem_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        return -1.0


# ============================================================
# 模型 sim_fn 构造(独立实例 + 独立缓存)
# ============================================================
def _build_sim_fn(model_key: str, model_name: str, timings: dict):
    from app.knowledge.embedding.sentence_transformer_embedding import SentenceTransformerEmbedding
    from app.evaluation.cache.embedding_cache import EvaluationEmbeddingCache
    from app.evaluation.runners.run_rag_eval import _make_sim_fn

    emb = SentenceTransformerEmbedding(model_name=model_name)
    cache = EvaluationEmbeddingCache(cache_dir=str(CACHE_ROOT / model_key))
    sim_fn = _make_sim_fn(emb, embedding_cache=cache, model_name=model_name,
                          timings=timings)
    return emb, cache, sim_fn


# ============================================================
# 主流程
# ============================================================
def main():
    if not DATA_PATH.exists():
        print(f'[ERROR] 未找到捕获数据 {DATA_PATH},请先运行 capture_archive_data.py')
        sys.exit(1)
    with open(DATA_PATH, encoding='utf-8') as f:
        samples = json.load(f)
    print(f'[数据] 已加载 {len(samples)} 题(question/ground_truth/answer/context_chunks 固定)')

    results = {}
    for key, model_name in MODELS.items():
        print(f'\n===== 模型: {key} ({model_name}) =====')
        t0 = time.time()
        timings: dict = {}
        emb, cache, sim_fn = _build_sim_fn(key, model_name, timings)
        t_load = time.time() - t0

        # ---- 预取全部文本(question/gt/answer/chunks/分句)----
        all_texts = []
        sent_map = {}
        for s in samples:
            all_texts += [s['question'], s['ground_truth'], s['answer']]
            all_texts += s['context_chunks']
            sent_map[s['index']] = _split_sents(s['answer'])
            all_texts += sent_map[s['index']]
        t_pref0 = time.time()
        sim_fn._prefetch(list(dict.fromkeys(all_texts)))  # type: ignore[attr-defined]
        t_pref = time.time() - t_pref0

        # ---- 每题 4 指标 + 相似度 ----
        from app.evaluation.metrics.rag_metrics import evaluate_single_sample
        per_question = []
        for s in samples:
            sc = evaluate_single_sample(s['question'], s['answer'],
                                        s['context_chunks'], s['ground_truth'],
                                        sim_fn=sim_fn)
            sim_qa = round(sim_fn(s['question'], s['answer']), 4)
            sim_gt_a = round(sim_fn(s['ground_truth'], s['answer']), 4)
            # 分句级(sentence-max similarity,diagnostic only)
            sents = sent_map[s['index']]
            sim_sent_max = round(max([sim_fn(s['question'], x) for x in sents], default=0.0), 4)
            per_question.append({
                'index': s['index'],
                'category': s.get('category', ''),
                'question_len': len(s['question']),
                'answer_len': len(s['answer']),
                'sim_question_answer': sim_qa,
                'sim_gt_answer': sim_gt_a,
                'sentence_max_sim': sim_sent_max,
                'sentence_count': len(sents),
                'scores': sc,
            })
        cache.flush()

        # ---- 聚合 ----
        agg = {}
        for m in ('faithfulness', 'answer_relevancy', 'context_precision', 'context_recall'):
            vals = [q['scores'][m] for q in per_question]
            agg[m] = {'mean': round(st.mean(vals), 4), 'distribution': _dist_stats(vals),
                      'pass_count': sum(1 for v in vals if v >= TARGETS[m]),
                      'total': len(vals)}
        sim_qa_vals = [q['sim_question_answer'] for q in per_question]
        sim_gt_vals = [q['sim_gt_answer'] for q in per_question]

        # ---- Spearman(question_len vs sim_qa / answer_len vs sim_qa)----
        q_lens = [q['question_len'] for q in per_question]
        a_lens = [q['answer_len'] for q in per_question]
        sp_q = _spearman(q_lens, sim_qa_vals)
        sp_a = _spearman(a_lens, sim_qa_vals)

        # ---- 分句级对比 ----
        whole = [q['sim_question_answer'] for q in per_question]
        sentmax = [q['sentence_max_sim'] for q in per_question]

        t_total = time.time() - t0
        results[key] = {
            'model_name': model_name,
            'aggregate': agg,
            'sim_question_answer': _dist_stats(sim_qa_vals),
            'sim_gt_answer': _dist_stats(sim_gt_vals),
            'spearman': {
                'question_len_vs_sim_qa': round(sp_q, 4),
                'answer_len_vs_sim_qa': round(sp_a, 4),
            },
            'sentence_level': {
                'whole_mean': round(st.mean(whole), 4),
                'sentence_max_mean': round(st.mean(sentmax), 4),
                'sentence_max_pass_085': sum(1 for v in sentmax if v >= 0.85),
            },
            'timing': {
                'load_s': round(t_load, 2),
                'prefetch_s': round(t_pref, 2),
                'embedding_infer_s': round(timings.get('embedding', 0.0), 2),
                'total_s': round(t_total, 2),
            },
            'per_question': per_question,
        }
        print(f"  F={agg['faithfulness']['mean']:.4f} AR={agg['answer_relevancy']['mean']:.4f} "
              f"CP={agg['context_precision']['mean']:.4f} CR={agg['context_recall']['mean']:.4f}")
        print(f"  sim(q,a) mean={results[key]['sim_question_answer']['mean']:.4f} "
              f"max={results[key]['sim_question_answer']['max']:.4f} "
              f"sim(gt,a) mean={results[key]['sim_gt_answer']['mean']:.4f}")
        print(f"  Spearman(q_len,sim)={sp_q:.4f} Spearman(a_len,sim)={sp_a:.4f}")
        print(f"  分句级 whole={st.mean(whole):.4f} sentence_max={st.mean(sentmax):.4f}")
        print(f"  耗时: 加载={t_load:.1f}s 预取={t_pref:.1f}s 推理={timings.get('embedding',0):.1f}s 总={t_total:.1f}s")

    # ---- 每题差异对比(large-small / m3-small)----
    per_q_map = {r['index']: r for r in results['bge-large']['per_question']}
    per_m3_map = {r['index']: r for r in results['bge-m3']['per_question']}
    per_small_map = {r['index']: r for r in results['bge-small']['per_question']}
    deltas = []
    for idx in sorted(per_small_map.keys()):
        small_ar = per_small_map[idx]['scores']['answer_relevancy']
        large_ar = per_q_map[idx]['scores']['answer_relevancy']
        m3_ar = per_m3_map[idx]['scores']['answer_relevancy']
        small_f = per_small_map[idx]['scores']['faithfulness']
        large_f = per_q_map[idx]['scores']['faithfulness']
        m3_f = per_m3_map[idx]['scores']['faithfulness']
        deltas.append({
            'index': idx,
            'category': per_small_map[idx]['category'],
            'small_AR': small_ar, 'large_AR': large_ar, 'm3_AR': m3_ar,
            'small_F': small_f, 'large_F': large_f, 'm3_F': m3_f,
            'large_minus_small_AR': round(large_ar - small_ar, 4),
            'm3_minus_small_AR': round(m3_ar - small_ar, 4),
            'large_minus_small_F': round(large_f - small_f, 4),
            'm3_minus_small_F': round(m3_f - small_f, 4),
        })
    deltas.sort(key=lambda d: d['large_minus_small_AR'], reverse=True)

    # ---- 资源占用 ----
    mem_after = _mem_rss_mb()

    summary = {
        'archived_baseline': ARCHIVED,
        'targets': TARGETS,
        'models': {k: v for k, v in results.items()},
        'per_question_deltas': deltas,
        'top_ar_gainers_large': deltas[:5],
        'top_ar_losers_large': list(reversed(deltas[-5:])),
        'top_f_gainers_large': sorted(deltas, key=lambda d: d['large_minus_small_F'], reverse=True)[:5],
        'top_f_losers_large': sorted(deltas, key=lambda d: d['large_minus_small_F'])[:5],
        'resources': {
            'device': 'CPU(本地无 GPU)',
            'process_rss_mb': round(mem_after, 1) if mem_after > 0 else None,
            'cache_dir': str(CACHE_ROOT),
        },
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f'\n[已输出] {OUT_PATH}')

    # ---- 控制台矩阵 ----
    print('\n===== 实验矩阵 =====')
    print(f"{'Model':<12} {'F':>7} {'AR':>7} {'CP':>7} {'CR':>7} {'AR>=0.85':>9} {'F>=0.85':>8}")
    for key, model_name in MODELS.items():
        r = results[key]
        a = r['aggregate']
        print(f"{key:<12} {a['faithfulness']['mean']:>7.4f} {a['answer_relevancy']['mean']:>7.4f} "
              f"{a['context_precision']['mean']:>7.4f} {a['context_recall']['mean']:>7.4f} "
              f"{a['answer_relevancy']['pass_count']}/{a['answer_relevancy']['total']:>5} "
              f"{a['faithfulness']['pass_count']}/{a['faithfulness']['total']}")
    print('\n===== sim(question,answer) / sim(gt,answer) =====')
    print(f"{'Model':<12} {'sim(q,a) mean':>14} {'sim(q,a) max':>12} {'sim(gt,a) mean':>14}")
    for key, model_name in MODELS.items():
        r = results[key]
        print(f"{key:<12} {r['sim_question_answer']['mean']:>14.4f} {r['sim_question_answer']['max']:>12.4f} "
              f"{r['sim_gt_answer']['mean']:>14.4f}")


if __name__ == '__main__':
    main()
