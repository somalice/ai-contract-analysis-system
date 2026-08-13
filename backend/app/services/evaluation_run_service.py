"""
Sprint 8.5 评估执行服务(RAG + AI + Summary 三态评估)

职责:
- run_evaluation: 执行一次完整评估(RAG 评估 + AI 调用统计 + Agent 工具统计 + 成本估算),
  复用 evaluation 模块现有组件,生成 build_summary 三态判定结果,
  持久化为 EvaluationReport 快照 + 落盘 evaluation_summary.json。
- get_latest_summary: 读取最近一次评估 summary(优先磁盘 summary.json,兜底 DB 最新快照)。
- list_history: 历史评估快照列表(复用 EvaluationReport 表,按 created_time DESC)。

复用组件(不重建):
- app.evaluation.runners.run_rag_eval.run_rag_evaluation
- app.evaluation.metrics.ai_metrics.analyze_ai_request_logs / analyze_agent_tools / estimate_cost
- app.evaluation.metrics.status_judge.build_summary
- app.models.evaluation_report.EvaluationReport (Sprint 8 已有表,不新增表)

约束:
- 不修改已有业务逻辑 / 数据库结构 / RAG 核心链路
- 所有写操作仅 EvaluationReport 表 + evaluation_summary.json 落盘
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from flask import current_app

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.evaluation_report import EvaluationReport
from app.models.evaluation_task import EvaluationTask
from app.models.knowledge_document import KnowledgeDocument


# evaluation_summary.json 落盘路径(backend/app/evaluation/reports/evaluation_summary.json)
def _summary_json_path() -> Path:
    return Path(current_app.root_path) / 'evaluation' / 'reports' / 'evaluation_summary.json'


def _dataset_path() -> str:
    return str(Path(current_app.root_path) / 'evaluation' / 'datasets' / 'contract_qa_dataset.json')


# ============================================================
# 0. 评估模式配置(Sprint 8.6.1 异步化: quick / standard / full)
# ============================================================
# 与前端 /evaluation/run 的 mode 字段对齐;不修改已有 evaluation_mode 语义。
EVALUATION_MODES = {
    # 10 题快速验证(开发调参, 不耗 Token)
    'quick': {
        'label': '10题快速验证',
        'sample_size': 10,
        'evaluation_mode': 'quick',
        'use_llm_answer': False,
    },
    # 51 题完整评估(生产验收, 规则级)
    # Sprint 8.8 修复: evaluation_mode 从 'quick' 修正为 'standard'。
    # 原缺陷导致 standard 走 quick 分支 → use_rerank=False(评估完全关闭 rerank),
    # 与 Sprint 8.6.1 设计(standard 保留 rerank)不符。修正后 standard =
    # answer_mode=context_extract + 跟随生产 RERANK_ENABLED(true)。
    'standard': {
        'label': '51题完整评估',
        'sample_size': None,  # None = 全量
        'evaluation_mode': 'standard',
        'use_llm_answer': False,
    },
    # 51 题 + LLM Judge(调用 DeepSeek 基于检索 context 生成 answer, 消耗 Token)
    'full': {
        'label': '51题 + LLM Judge',
        'sample_size': None,
        'evaluation_mode': 'production',
        'use_llm_answer': True,
    },
}


# ============================================================
# 1. 执行评估
# ============================================================
def run_evaluation(
    user_id: Optional[int] = None,
    sample_size: Optional[int] = None,
    use_llm_answer: bool = False,
    period_days: int = 60,
    persist: bool = True,
    evaluation_mode: str = 'quick',
    progress_callback: Optional[Any] = None,
    rag_progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    执行一次完整 AI 评估。

    :param user_id: 触发评估的用户 ID
    :param sample_size: RAG 数据集采样数(None=全量 51 题)
    :param use_llm_answer: 是否调用真实 LLM 生成回答(消耗 Token)
    :param period_days: AI 调用日志统计天数
    :param persist: 是否持久化为 EvaluationReport 快照
    :param evaluation_mode: Sprint 8.6 收尾 双模式 Answer 生成策略
        - 'quick'(默认): 开发调参, answer=ground_truth, 不消耗 Token
        - 'production': 发布验收, 调用 DeepSeek 基于检索 context 生成 answer(use_llm_answer=True)
    :param progress_callback: Sprint 8.6.1 异步任务阶段进度回调 (percent: int, stage: str)
    :param rag_progress_callback: Sprint 8.6.1 RAG 题级进度回调 (done: int, total: int)
    :return: summary dict(build_summary 产物 + report_no)
    """
    from app.evaluation.runners.run_rag_eval import run_rag_evaluation
    from app.evaluation.metrics.ai_metrics import (
        analyze_ai_request_logs,
        analyze_agent_tools,
        estimate_cost,
    )
    from app.evaluation.metrics.status_judge import build_summary
    from app.models.ai_request_log import AIRequestLog
    from app.models.review_report import ReviewReport
    from app.models.generated_contract import GeneratedContract
    from app.models.generated_proposal import GeneratedProposal

    def _emit(percent: int, stage: str):
        if progress_callback is not None:
            try:
                progress_callback(percent, stage)
            except Exception:
                pass

    t0 = datetime.utcnow()
    logger.info('[EvalRun] 开始执行 AI 评估: sample_size=%s use_llm=%s mode=%s start_time=%s',
                sample_size, use_llm_answer, evaluation_mode,
                t0.strftime('%Y-%m-%d %H:%M:%S'))

    # ---------- 1. RAG 评估 ----------
    _emit(2, 'rag_evaluation')
    rag_eval = run_rag_evaluation(
        app=current_app,
        db_session=db.session,
        dataset_path=_dataset_path(),
        sample_size=sample_size,
        use_llm_answer=use_llm_answer,
        evaluation_mode=evaluation_mode,
        progress_callback=rag_progress_callback,
    )
    t1 = datetime.utcnow()
    rag_eval_time = (t1 - t0).total_seconds()

    # ---------- 2. AI 调用质量 + Agent 工具 + 成本 ----------
    _emit(65, 'ai_metrics')
    ai_overview = analyze_ai_request_logs(db.session, AIRequestLog, period_days=period_days)
    agent_tools = analyze_agent_tools(
        db.session,
        [ReviewReport, GeneratedContract, GeneratedProposal],
        period_days=period_days,
    )
    cost = estimate_cost(
        sum_input_tokens=ai_overview.get('sum_input_tokens', 0),
        sum_output_tokens=ai_overview.get('sum_output_tokens', 0),
    )
    ai_stats = {'ai_overview': ai_overview, 'agent_tools': agent_tools, 'cost': cost}
    t2 = datetime.utcnow()
    ai_metric_time = (t2 - t1).total_seconds()

    # ---------- 3. 知识库统计 ----------
    _emit(78, 'agent_metrics')
    knowledge_stats = _knowledge_stats(rag_eval)

    # ---------- 4. 三态判定 + summary 结构化 ----------
    _emit(88, 'report_generation')
    summary = build_summary(rag_eval, ai_stats, knowledge_stats)
    summary['eval_duration_ms'] = rag_eval.get('duration_ms', 0)
    summary['run_duration_ms'] = int((datetime.utcnow() - t0).total_seconds() * 1000)

    # ---------- 5. 持久化 ----------
    report_no = None
    if persist:
        report_no = _persist_summary(summary, user_id)
        summary['report_no'] = report_no

        # 落盘 evaluation_summary.json(前端 /summary 接口优先读取)
        _write_summary_json(summary)
    t3 = datetime.utcnow()
    report_save_time = (t3 - t2).total_seconds()
    total_time = (t3 - t0).total_seconds()

    # Sprint 8.6 收尾修复: 分段耗时日志(定位长耗时环节)
    logger.info(
        '[EvalRun] 分段耗时: rag_eval=%.2fs ai_metric=%.2fs report_save=%.2fs '
        'total=%.2fs (start=%s, rag_eval_time=%.2f, ai_metric_time=%.2f, '
        'report_save_time=%.2f, total_time=%.2f)',
        rag_eval_time, ai_metric_time, report_save_time, total_time,
        t0.strftime('%Y-%m-%d %H:%M:%S'),
        rag_eval_time, ai_metric_time, report_save_time, total_time,
    )
    logger.info('[EvalRun] Evaluation completed in %.2f seconds | status=%s report_no=%s',
                total_time, summary.get('status'), report_no)
    _emit(100, 'completed')
    return summary


def _knowledge_stats(rag_eval: Dict[str, Any]) -> Dict[str, Any]:
    """统计知识库现状(总文档/命中文档/embedding 完成数/命中率)。"""
    try:
        total_docs = KnowledgeDocument.query.filter_by(status='active').count()
        emb_completed = (
            KnowledgeDocument.query
            .filter_by(status='active', embedding_status='completed')
            .count()
        )
    except Exception as e:
        logger.warning('[EvalRun] 知识库统计失败: %s', e)
        total_docs = 0
        emb_completed = 0

    hit_docs = rag_eval.get('hit_document_count', 0) or len(rag_eval.get('hit_document_ids', []) or [])
    hit_rate = round(hit_docs / total_docs, 4) if total_docs > 0 else 0.0
    return {
        'total_documents': total_docs,
        'hit_documents': hit_docs,
        'embedding_completed': emb_completed,
        'hit_rate': hit_rate,
    }


def _persist_summary(summary: Dict[str, Any], user_id: Optional[int]) -> Optional[str]:
    """将 summary 持久化为 EvaluationReport 快照(metrics 字段存完整 summary)。"""
    try:
        rpt = EvaluationReport(
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
            metrics=summary,
            summary=_build_human_summary(summary),
            generated_by=user_id,
        )
        db.session.add(rpt)
        db.session.commit()
        return rpt.report_no
    except Exception as e:
        db.session.rollback()
        logger.exception('[EvalRun] 持久化 EvaluationReport 失败: %s', e)
        return None


def _build_human_summary(s: Dict[str, Any]) -> str:
    """生成人类可读摘要(存入 EvaluationReport.summary)。"""
    lines = [
        f"AI 评估 {s.get('generated_at', '')}: 状态={s.get('status', '')} ({s.get('status_label', '')})。",
        f"RAG: {s.get('total_questions', 0)} 题, 命中 {s.get('context_hit_count', 0)} (命中率 {s.get('context_hit_rate', 0):.1%}), "
        f"Faithfulness={s.get('faithfulness', 0)}, Recall={s.get('context_recall', 0)}。",
        f"AI 稳定性: {s.get('ai_total_calls', 0)} 次调用, 成功率 {s.get('ai_success_rate', 0):.1%}, "
        f"P95={s.get('ai_p95_latency_ms')}ms。",
        f"成本: {s.get('total_tokens', 0)} tokens, ≈ ¥{s.get('estimated_cost_rmb', 0)}。",
        f"Agent: 任务 {s.get('agent_task_total', 0)}, 完成率 {s.get('agent_completion_rate', 0):.1%}, "
        f"工具调用 {s.get('tool_call_total', 0)} 次, 成功率 {s.get('tool_success_rate', 0):.1%}。",
        f"知识库: {s.get('test_environment', {}).get('knowledge_total_documents', 0)} 份文档, "
        f"命中 {s.get('test_environment', {}).get('knowledge_hit_documents', 0)} 份。",
        f"原因: {s.get('reason', '')}",
    ]
    return '\n'.join(lines)


def _write_summary_json(summary: Dict[str, Any]) -> None:
    """落盘 evaluation_summary.json(供 /summary 接口快速读取)。"""
    try:
        path = _summary_json_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info('[EvalRun] summary 已落盘: %s', path)
    except Exception as e:
        logger.warning('[EvalRun] summary 落盘失败(不影响业务): %s', e)


# ============================================================
# 2. 读取最新 summary
# ============================================================
def get_latest_summary() -> Optional[Dict[str, Any]]:
    """
    读取最新评估 summary。
    优先读 evaluation_summary.json(快);无则读 EvaluationReport 最新快照。
    """
    # 优先读磁盘
    try:
        path = _summary_json_path()
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning('[EvalRun] 读取 summary.json 失败,回退 DB: %s', e)

    # 兜底:读 DB 最新快照
    rpt = (
        EvaluationReport.query
        .order_by(EvaluationReport.created_time.desc())
        .first()
    )
    if rpt and isinstance(rpt.metrics, dict):
        d = rpt.metrics
        d.setdefault('report_no', rpt.report_no)
        d.setdefault('generated_at', rpt.created_time.strftime('%Y-%m-%d %H:%M:%S'))
        return d
    return None


# ============================================================
# 3. 历史快照列表
# ============================================================
def list_history(page: int = 1, size: int = 20) -> Dict[str, Any]:
    """
    历史评估快照列表(精简字段,供前端历史表格展示)。
    """
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(int(size), 100))
    except (TypeError, ValueError):
        size = 20

    total = EvaluationReport.query.count()
    rows = (
        EvaluationReport.query
        .order_by(EvaluationReport.created_time.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    items = [_history_item(r) for r in rows]
    return {'total': total, 'page': page, 'size': size, 'items': items}


def _history_item(r: EvaluationReport) -> Dict[str, Any]:
    """从 EvaluationReport 提取历史列表所需精简字段(从 metrics JSON 摘取关键指标)。"""
    m = r.metrics if isinstance(r.metrics, dict) else {}
    env = m.get('test_environment', {}) if isinstance(m, dict) else {}
    return {
        'id': r.id,
        'report_no': r.report_no,
        'created_time': r.created_time.strftime('%Y-%m-%d %H:%M:%S') if r.created_time else None,
        'generated_by_username': r.creator.username if r.creator else None,
        'status': m.get('status'),
        'status_label': m.get('status_label'),
        'total_questions': m.get('total_questions', 0),
        'context_hit_rate': m.get('context_hit_rate', 0),
        'faithfulness': m.get('faithfulness', 0),
        'answer_relevancy': m.get('answer_relevancy', 0),
        'context_precision': m.get('context_precision', 0),
        'context_recall': m.get('context_recall', 0),
        'ai_success_rate': m.get('ai_success_rate', 0),
        'ai_p95_latency_ms': m.get('ai_p95_latency_ms'),
        'tool_success_rate': m.get('tool_success_rate', 0),
        'knowledge_total_documents': env.get('knowledge_total_documents', 0),
        'knowledge_hit_documents': env.get('knowledge_hit_documents', 0),
        'reason': m.get('reason'),
    }


def get_history_detail(report_id: int) -> Optional[Dict[str, Any]]:
    """历史快照详情(完整 metrics)。"""
    try:
        rid = int(report_id)
    except (TypeError, ValueError):
        return None
    rpt = db.session.get(EvaluationReport, rid)
    if not rpt:
        return None
    d = rpt.to_dict(include_metrics=True)
    return d


# ============================================================
# 4. 异步任务管理(Sprint 8.6.1 - POST /evaluation/run 异步化)
# ============================================================
def create_evaluation_task(
    user_id: Optional[int] = None,
    evaluation_mode: str = 'quick',
    sample_size: Optional[int] = None,
    use_llm_answer: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    创建异步评估任务并立即返回(后台线程执行完整评估)。

    :param user_id: 触发人
    :param evaluation_mode: quick(10题) / standard(51题) / full(51题+LLM Judge)
    :param sample_size: 显式覆盖题数(None=按模式默认)
    :param use_llm_answer: 显式覆盖是否 LLM 生成(None=按模式默认)
    :return: 任务 dict(立即返回,不阻塞)
    """
    # 模式解析:非法模式回退 quick
    mode_cfg = EVALUATION_MODES.get(evaluation_mode)
    if mode_cfg is None:
        evaluation_mode = 'quick'
        mode_cfg = EVALUATION_MODES['quick']

    effective_sample_size = sample_size if sample_size is not None else mode_cfg['sample_size']
    effective_llm = use_llm_answer if use_llm_answer is not None else mode_cfg['use_llm_answer']

    task = EvaluationTask(
        status='pending',
        progress=0,
        current_stage='creating',
        evaluation_mode=evaluation_mode,
        sample_size=effective_sample_size,
        use_llm_answer=effective_llm,
        generated_by=user_id,
    )
    db.session.add(task)
    db.session.commit()
    task_id = task.task_id

    logger.info('[EvalTask] 创建任务 %s | mode=%s sample=%s use_llm=%s user=%s',
                task_id, evaluation_mode, effective_sample_size, effective_llm, user_id)

    # 捕获当前 app 实例,后台线程 push app context 使用(与请求共享同一应用对象)
    try:
        app = current_app._get_current_object()
    except Exception:
        app = None

    t = threading.Thread(
        target=_run_task_worker,
        args=(task_id, app),
        daemon=True,
        name=f'eval-task-{task_id}',
    )
    t.start()
    return task.to_dict()


def _run_task_worker(task_id: str, app) -> None:
    """后台线程入口:在 app context 中执行完整评估。"""
    try:
        if app is None:
            from app import create_app
            app = create_app()
        with app.app_context():
            _execute_task(task_id)
    except Exception as e:
        # 兜底:标记失败
        try:
            task = EvaluationTask.query.filter_by(task_id=task_id).first()
            if task:
                task.status = 'failed'
                task.error = f'任务执行异常: {e}'[:2000]
                task.end_time = datetime.utcnow()
                db.session.commit()
        except Exception:
            db.session.rollback()
        logger.exception('[EvalTask] %s 后台执行异常: %s', task_id, e)


def _execute_task(task_id: str) -> None:
    """任务核心执行(含进度上报 / 失败处理)。"""
    task = EvaluationTask.query.filter_by(task_id=task_id).first()
    if not task:
        logger.warning('[EvalTask] 任务不存在: %s', task_id)
        return

    # 进入运行态
    task.status = 'running'
    task.start_time = datetime.utcnow()
    task.current_stage = 'rag_evaluation'
    task.progress = 2
    db.session.commit()

    # 说明:回调可能在嵌套 app context(RAG 评估内部)中调用,
    # scoped_session 绑定最内层 app context,故必须用当前 db.session 重新查询 task,
    # 不能直接修改闭包捕获的 task(它属于外层 session,提交会丢失)。
    def _on_progress(percent: int, stage: str):
        """阶段级进度上报(由 run_evaluation 回调)"""
        try:
            t = EvaluationTask.query.filter_by(task_id=task_id).first()
            if t is None:
                return
            t.progress = max(t.progress, percent)
            t.current_stage = stage
            t.updated_time = datetime.utcnow()
            db.session.commit()
        except Exception as _pe:
            db.session.rollback()
            logger.warning('[EvalTask] %s 阶段进度上报失败: %s', task_id, _pe)

    def _on_rag(done: int, total: int):
        """RAG 题级进度 → 5%~62%"""
        if total <= 0:
            return
        pct = 5 + int((done / total) * 57)
        try:
            t = EvaluationTask.query.filter_by(task_id=task_id).first()
            if t is None:
                return
            t.progress = max(t.progress, min(pct, 62))
            t.current_stage = 'rag_evaluation'
            t.updated_time = datetime.utcnow()
            db.session.commit()
        except Exception as _ce:
            db.session.rollback()
            logger.warning('[EvalTask] %s RAG进度上报失败: %s', task_id, _ce)

    try:
        summary = run_evaluation(
            user_id=task.generated_by,
            sample_size=task.sample_size,
            use_llm_answer=task.use_llm_answer,
            evaluation_mode=task.evaluation_mode,
            persist=True,
            progress_callback=_on_progress,
            rag_progress_callback=_on_rag,
        )
        # 成功(重新查询当前 session 下的 task,避免嵌套 app context 导致 session 归属不一致)
        t = EvaluationTask.query.filter_by(task_id=task_id).first()
        if t:
            t.status = 'success'
            t.progress = 100
            t.current_stage = 'completed'
            t.report_id = summary.get('report_no')
            t.end_time = datetime.utcnow()
            db.session.commit()
        logger.info('[EvalTask] %s 完成 | report=%s status=%s',
                    task_id, summary.get('report_no'), summary.get('status'))
    except Exception as e:
        db.session.rollback()
        t = EvaluationTask.query.filter_by(task_id=task_id).first()
        if t:
            t.status = 'failed'
            t.current_stage = 'failed'
            t.error = str(e)[:2000]
            t.end_time = datetime.utcnow()
            db.session.commit()
        logger.exception('[EvalTask] %s 执行失败: %s', task_id, e)


def get_evaluation_task(task_id: str) -> Optional[Dict[str, Any]]:
    """查询任务状态(供 GET /evaluation/task/{task_id} 轮询)。"""
    if not task_id:
        return None
    task = EvaluationTask.query.filter_by(task_id=task_id).first()
    if not task:
        return None
    return task.to_dict()
