"""
业务服务层包

Sprint 1: auth_service
Sprint 2: contract_service
Sprint 3: document_service / analysis_service
Sprint 6: generation_service
Sprint 7: bid_service
Sprint 8 新增: cache_service / ai_log_service / prompt_service / evaluation_service

所有新模块在此处导入,使 `from app import services` + `services.xxx.xxx()` 可用。
"""
from . import auth_service       # noqa: F401
from . import contract_service   # noqa: F401
from . import document_service   # noqa: F401
from . import analysis_service   # noqa: F401
from . import generation_service  # noqa: F401
from . import bid_service        # noqa: F401

# ---------- Sprint 8 新增企业级能力服务 ----------
from . import cache_service      # noqa: F401  Redis + 内存降级统一缓存
from . import ai_log_service     # noqa: F401  AI 调用日志(AIRequestLog)
from . import prompt_service     # noqa: F401  Prompt DB 管理 + 文件回退
from . import evaluation_service # noqa: F401  AI 评估统计(报告聚合)

# ---------- Sprint 8.5 新增:AI 评估执行(RAG + 三态判定) ----------
from . import evaluation_run_service  # noqa: F401  RAG 评估执行 + summary 三态判定
