# Sprint 8.9 - Production Regression Verification 报告

- 版本: v1.0.0 Release Candidate
- 执行时间: 2026-08-11 17:39 - 17:50
- 目的: 验证当前生产 RAG 链路是否回归 Sprint 8.9 归档基线
- 范围: **仅回归验证**;未修改 RAG 算法 / 评估指标 / 阈值 / dataset / ground_truth / 知识库 / embedding

---

## 1. Phase 1:生产链路配置复核

### 1.1 production/full 评估模式链路确认(代码级)

| 检查项 | 结论 | 证据 |
|--------|------|------|
| 调用 `query_rag()` | ✅ 走真实生产链路 | `run_rag_eval.py:699-713` production 分支 `answer_mode='llm'` → `query_rag(question, user)` |
| 不使用 ground_truth 作为 answer | ✅ answer=query_rag 输出 | `use_llm_answer=True`;ground_truth 仅用于指标打分 |
| Answer 模式 | ✅ `RAG_ANSWER_MODE=extract` | `.env:88` → `settings.py:128` → `rag_service.py:601` extract 分支(长句化抽取) |
| Rerank 开启 | ✅ `RERANK_ENABLED=true` | `run_rag_eval.py:628-629` use_rerank=None → 跟随 config=true;`rag_service.py:554` |
| RERANK_RECALL_K | ✅ 10 | `.env:68` → `rag_service.py:555` / `_retrieve_chunks` |
| RERANK_FINAL_TOP_K | ✅ 3 | `.env:69` → `rag_service.py:562` |
| RETRIEVER_TOP_K | ✅ 10 | `.env:65` → retriever 构造;运行日志 `top_k=10 命中=10` |
| Embedding 模型 | ✅ `BAAI/bge-small-zh-v1.5` | `settings.py:75` → `vector_store_registry.py:54` |
| 不使用 quick evaluator 抽取逻辑 | ✅ | quick 专属 `_extract_relevant_sentences` 仅在 standard/quick 分支;production 走 query_rag |

### 1.2 配置一致性

`.env` 生产配置与归档实验配置 `scripts/s89_extract_topk3_config.json` **完全一致**(RERANK_ENABLED=true / RERANK_RECALL_K=10 / RERANK_FINAL_TOP_K=3 / RAG_ANSWER_MODE=extract / RAG_EXTRACT_TOP_N=3 / RAG_EXTRACT_MIN_SIM=0.55)。

### 1.3 执行命令(与归档基线同链路)

```bash
python scripts/run_phase4_eval.py --label s89_prod_regression \
  --mode production --config-file scripts/s89_extract_topk3_config.json \
  --no-rag-cache --json-out scripts/s89_prod_regression.json --md-out scripts/s89_prod_regression.md
```

- `--no-rag-cache`:评估前清空 rag 查询缓存,避免历史结果污染;
- 运行日志确认:51 题均真实调用 `query_rag`(`RAG 查询: user=eval_agent`,`检索: top_k=10 命中=10`)。

---

## 2. Phase 3:与 Sprint 8.9 基线对比(51 题全量 production)

### 2.1 核心指标

| Metric | Sprint 8.9 Baseline | Current | Delta | Status |
|--------|--------------------:|--------:|------:|--------|
| Faithfulness | 0.8382 | **0.8382** | **0.0000** | **PASS** |
| Answer Relevancy | 0.7373 | **0.7373** | **0.0000** | **PASS**(保持归档值) |
| Context Precision | 0.8117 | **0.8117** | **0.0000** | **PASS** |
| Context Recall | 0.8233 | **0.8233** | **0.0000** | **PASS** |

> 4 项指标与基线**四位小数完全一致(零漂移)**,证明当前生产链路与 Sprint 8.9 归档链路 100% 复现。

### 2.2 通过率与知识覆盖(当前)

| 指标 | 均值 | 通过率 | 目标 |
|------|------|--------|------|
| Faithfulness | 0.8382 | 41.2%(21/51) | ≥0.85 |
| Answer Relevancy | 0.7373 | 0%(0/51) | ≥0.85 |
| Context Precision | 0.8117 | 56.9%(29/51) | ≥0.80 |
| Context Recall | 0.8233 | 60.8%(31/51) | ≥0.80 |

| 覆盖项 | 值 |
|--------|-----|
| 检索命中率(retriever_hit_rate) | 1.0(51/51) |
| 检索正确率(retrieved_correct_rate) | 0.9412 |
| 有效覆盖率(effective_coverage_rate) | 0.8824 |
| covered / partial / not_covered | 32 / 13 / 6 |

### 2.3 性能与运行特征

| 项 | 值 | 说明 |
|----|-----|------|
| 总耗时(total_seconds) | 647.71s(≈10.8min) | 4 worker 并行,含完整 rerank |
| P50 / P95(每题延迟) | N/A | 评估器未输出每题延迟分位;单题耗时≈total/51≈12.7s(含并行摊薄) |
| LLM 调用次数 | **0** | `RAG_ANSWER_MODE=extract`,embedding 段落级抽取,零 LLM 成本 |
| AI 成功率 | 100%(N/A) | 无 LLM 调用,llm_error 全为 None |
| RAG 命中率 | 100%(51/51) | 每题检索均命中 ≥1 相关文档 |
| rerank 耗时(rerank_seconds) | 811.28s | 4 worker 累计(瓶颈,单题 ~15.9s) |
| embedding 耗时 | 0.0s | 评估器 sim_fn 命中持久化 embedding 缓存,零推理 |
| retrieval 耗时 | 138.9s | 4 worker 累计(dense 检索 + query 编码) |
| cache 命中率 | 0.0% | `--no-rag-cache` 清空后全量重算,避免污染 |

---

## 3. Phase 4:最终结论

**结论:PASS — 当前生产链路无回归。**

依据:

1. **4 项指标与 Sprint 8.9 归档基线完全一致(Delta=0.0000)**;
2. 评估链路复核通过:production 模式真实调用 `query_rag()`,answer 来自 `RAG_ANSWER_MODE=extract` 长句化抽取,未使用 ground_truth、未关闭 rerank、未用 quick 抽取逻辑;
3. 配置一致:`.env` 与归档 config 文件逐项相同(extract / top_k=10 / rerank recall10→final3 / bge-small-zh-v1.5);
4. 运行日志佐证:51 题全部 `query_rag` 真实调用 + `top_k=10 命中=10`;
5. 已清空 rag 缓存,结果无历史污染。

**关于 Answer Relevancy**:当前值 0.7373 与基线一致(非回归)。其与目标 0.85 的差距维持 Sprint 8.9 既有结论——bge-small-zh-v1.5 对"短问题 vs 长答案"余弦上界约 0.83,51 题 `sim(question,answer)` 全部 <0.85,属评估 embedding 模型度量限制,非链路回归。本阶段**未修改指标阈值**。

---

## 4. 归档与追溯

| 文件 | 内容 |
|------|------|
| `scripts/s89_prod_regression.json` | 本次全量明细(51 题 scores/coverage/performance) |
| `scripts/s89_prod_regression.md` | 本次评估 Markdown 报告 |
| `docs/SPRINT8_9_PRODUCTION_REGRESSION_REPORT.md` | 本报告 |
| `docs/SPRINT8_9_RAG_ANSWER_OPTIMIZATION_REPORT.md` | Sprint 8.9 实验报告(基线来源) |
| `docs/SPRINT8_9_REGRESSION_CONFIG_CHECK.md` | 前置配置差异检查报告 |
