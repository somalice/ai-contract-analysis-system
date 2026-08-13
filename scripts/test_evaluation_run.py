"""Sprint 8.5 评估运行验证脚本(临时,用于验证 RAG 命中率与三态判定)。

Sprint 8.7 扩展:
- --clear-cache  : 清空评估缓存(context cache + embedding cache)后退出
- --sample=N     : 采样题数(默认 None=全量 51 题;quick 建议 --sample=10)
- --mode=MODE    : quick / standard / full(默认 quick)
- 输出增加 performance 字段(各阶段耗时 + cache 命中率)
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

from app import create_app
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / 'backend' / '.env')

app = create_app()

parser = argparse.ArgumentParser(description='AI 评估运行验证')
parser.add_argument('--clear-cache', action='store_true', help='清空评估缓存(context+embedding)后退出')
parser.add_argument('--sample', type=int, default=None, help='RAG 采样题数(默认按模式)')
parser.add_argument('--mode', default='quick', help='评估模式 quick/standard/full(默认 quick)')
parser.add_argument('--persist', action='store_true', help='持久化为 EvaluationReport 快照')
args = parser.parse_args()

with app.app_context():
    from app.evaluation.cache import EvaluationContextCache, EvaluationEmbeddingCache
    if args.clear_cache:
        cache_dir = Path(app.root_path) / 'evaluation' / 'cache'
        n_ctx = EvaluationContextCache(str(cache_dir)).clear()
        emb = EvaluationEmbeddingCache(str(cache_dir))
        emb.clear()
        print(f'[ClearCache] context cache 清除 {n_ctx} 条, embedding cache 已清空')
        print('[ClearCache] 缓存文件:')
        for p in sorted(cache_dir.glob('evaluation_*_cache.json')):
            print('  存在:', p.name)
        for p in sorted(cache_dir.glob('evaluation_*_cache.json')):
            if not p.exists():
                print('  已删除:', p.name)
        sys.exit(0)

    from app.services import evaluation_run_service
    summary = evaluation_run_service.run_evaluation(
        user_id=1, sample_size=args.sample, use_llm_answer=False,
        period_days=60, persist=args.persist, evaluation_mode=args.mode,
    )
    print('===== 评估结果 =====')
    print('状态:', summary.get('status'), '(', summary.get('status_label'), ')')
    print('总问题数:', summary.get('total_questions'))
    print('命中问题数:', summary.get('context_hit_count'))
    print('命中率:', summary.get('context_hit_rate'))
    print('Faithfulness:', summary.get('faithfulness'))
    print('Answer Relevancy:', summary.get('answer_relevancy'))
    print('Context Precision:', summary.get('context_precision'))
    print('Context Recall:', summary.get('context_recall'))
    print('AI 成功率:', summary.get('ai_success_rate'))
    print('P95:', summary.get('ai_p95_latency_ms'), 'ms')
    env = summary.get('test_environment', {}) or {}
    print('知识库总文档:', env.get('knowledge_total_documents'))
    print('命中文档:', env.get('knowledge_hit_documents'))
    print('知识库命中率:', env.get('knowledge_hit_rate'))
    print('RAG 子状态:', summary.get('rag_status', {}).get('status'))
    print('AI 子状态:', summary.get('ai_status', {}).get('status'))
    print('原因:', summary.get('reason'))
    print('report_no:', summary.get('report_no'))
    print('运行耗时(ms):', summary.get('run_duration_ms'))
    perf = summary.get('performance') or {}
    if perf:
        print('===== 性能统计(Sprint 8.7) =====')
        print('总耗时(s):', perf.get('total_seconds'))
        print('embedding 耗时(s):', perf.get('embedding_seconds'))
        print('dense 检索耗时(s):', perf.get('retrieval_seconds'))
        print('rerank 耗时(s):', perf.get('rerank_seconds'))
        print('指标计算耗时(s):', perf.get('metric_seconds'))
        print('cache 命中率:', perf.get('cache_hit_rate'),
              f"({perf.get('cache_hit_count')}/{perf.get('cache_total_count')})")
        print('并行 worker:', perf.get('parallel_workers'))
        print('use_rerank:', perf.get('use_rerank'))
    else:
        print('(无 performance 字段,请确认 run_rag_evaluation 已返回 Sprint 8.7 performance)')
