"""
Flask 应用工厂(Application Factory)

职责:
- 创建 Flask 实例
- 加载配置(config.get_config())
- 初始化扩展(db / jwt / logger)
- 创建数据库表(db.create_all,Sprint 1 起)
- 注册全局错误处理器
- 注册 Blueprint

不包含业务逻辑;业务逻辑分布在 api/services/ai 各层。
"""
import os
from flask import Flask
from app.config import get_config


def create_app(config_class=None):
    """
    创建并配置 Flask 应用实例
    :param config_class: 可选,显式指定配置类(测试时使用);默认按 FLASK_ENV 选择
    :return: Flask app
    """
    app = Flask(__name__, template_folder='templates')

    # 加载配置
    app.config.from_object(config_class or get_config())

    # 确保上传目录存在
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ---------- 初始化扩展 ----------
    # 日志(最先初始化,后续步骤可记录日志)
    from app.extensions.logger import setup_logging
    setup_logging(app)

    # 数据库(Sprint 1 起:init_app + create_all)
    from app.extensions.db import db
    db.init_app(app)

    # JWT(Sprint 1)
    from app.extensions.jwt import init_jwt
    init_jwt(app)

    # CORS(Sprint 2 - v0.4.0 前端 Admin Console 基础设施)
    # 仅对 /api/* 开放,Origin 白名单从 .env 读取,禁止 "*"
    from app.extensions.cors import init_cors
    init_cors(app)

    # Redis(Sprint 8 - v1.0.0:可选客户端,不可用时自动降级为内存缓存;
    # 本 init 永不抛出,失败仅 logger.warning)
    from app.extensions import init_redis
    init_redis(app)

    # ---------- 创建数据库表 ----------
    # Sprint 1 起:在 app context 内创建所有已注册的 Model 表(users 等)
    # Sprint 2 起:新增 Contract 模型(contracts 表)
    # Sprint 3 起:新增 Document / AnalysisTask / ContractField 模型
    # Sprint 4 起:新增 KnowledgeDocument / KnowledgeChunk 模型(知识库 / RAG)
    # Sprint 5 起:新增 ReviewReport 模型(合同审核 Agent)
    # Sprint 6 起:新增 ContractTemplate / GeneratedContract 模型(模板中心 / 合同生成)
    # Sprint 7 起:新增 BidDocument / BidRequirement / GeneratedProposal / ProposalSection 模型
    # Sprint 8 起:新增 AIRequestLog / OperationLog / PromptTemplate / EvaluationReport 模型(企业级能力)
    with app.app_context():
        from app.models.user import User  # noqa: F401 确保模型被导入注册
        from app.models.contract import Contract  # noqa: F401 确保模型被导入注册
        from app.models.document import Document  # noqa: F401 Sprint 3 新增
        from app.models.analysis_task import AnalysisTask  # noqa: F401 Sprint 3 新增
        from app.models.contract_field import ContractField  # noqa: F401 Sprint 3 新增
        from app.models.knowledge_document import KnowledgeDocument  # noqa: F401 Sprint 4 新增
        from app.models.knowledge_chunk import KnowledgeChunk  # noqa: F401 Sprint 4 新增
        from app.models.review_report import ReviewReport  # noqa: F401 Sprint 5 新增
        from app.models.contract_template import ContractTemplate  # noqa: F401 Sprint 6 新增
        from app.models.generated_contract import GeneratedContract  # noqa: F401 Sprint 6 新增
        from app.models.bid_document import BidDocument  # noqa: F401 Sprint 7 新增
        from app.models.bid_requirement import BidRequirement  # noqa: F401 Sprint 7 新增
        from app.models.generated_proposal import GeneratedProposal  # noqa: F401 Sprint 7 新增
        from app.models.proposal_section import ProposalSection  # noqa: F401 Sprint 7 新增
        # Sprint 8 新增:企业级能力
        from app.models.ai_request_log import AIRequestLog  # noqa: F401
        from app.models.operation_log import OperationLog  # noqa: F401
        from app.models.prompt_template import PromptTemplate  # noqa: F401
        from app.models.evaluation_report import EvaluationReport  # noqa: F401
        from app.models.evaluation_task import EvaluationTask  # noqa: F401 Sprint 8.6.1 评估异步任务
        db.create_all()

        # ---------- 初始化向量库(Sprint 4)----------
        # 启动时加载已存在的 FAISS 索引(若文件存在);失败不阻断启动
        # 注:embedding 模型懒加载,此处仅加载已落盘的 FAISS 索引
        from app.knowledge.services import vector_store_registry
        try:
            vector_store_registry.load(app)
        except Exception as e:
            from app.extensions.logger import logger
            logger.warning('向量库加载失败(不影响启动,首次上传时会重建): %s', e)

    # ---------- 注册全局错误处理器 ----------
    from app.utils.exceptions import register_error_handlers
    register_error_handlers(app)

    # ---------- Sprint 8: 操作审计中间件 ----------
    # 记录登录/合同/知识库/投标关键操作;审计失败绝不影响响应(全程 try/except 保护)
    try:
        from app.middleware.audit_middleware import register_audit_middleware
        register_audit_middleware(app)

        # before_request:写入 AUDIT_START_TS, 保证 duration 精度
        import time
        @app.before_request
        def _record_start_ts():
            from flask import request as _req
            _req.environ['AUDIT_START_TS'] = time.time()
    except Exception as _e:
        from app.extensions.logger import logger
        logger.warning('[Sprint8] 审计中间件注册失败(不影响主流程): %s', _e)

    # ---------- 注册 Blueprint(局部导入,避免循环依赖)----------
    # 合同上传页(HTML)
    from app.api.contract.routes import contract_bp
    app.register_blueprint(contract_bp)

    # 系统模块(健康检查等,前缀 /api/v1)
    from app.api.system.routes import system_bp
    app.register_blueprint(system_bp, url_prefix='/api/v1')

    # 认证模块(注册/登录/profile,前缀 /api/v1/auth)
    from app.api.auth.routes import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')

    # 合同管理 RESTful API(Sprint 2 - v0.4.0,前缀 /api/v1/contracts)
    # 注:contract_bp(HTML 上传页)已在上方注册,此处为独立的 JSON API Blueprint
    from app.api.contract.routes import contract_api_bp
    app.register_blueprint(contract_api_bp, url_prefix='/api/v1/contracts')

    # 分析任务 API(Sprint 3 - v0.5.0,前缀 /api/v1/analysis)
    # 提供 GET /api/v1/analysis/{task_id} 任务状态查询
    from app.api.analysis.routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/api/v1/analysis')

    # 知识库管理 API(Sprint 4 - v0.6.0,前缀 /api/v1/knowledge)
    # 提供 上传 / 列表 / 详情 / 删除 知识文档
    from app.knowledge.api.routes import knowledge_bp
    app.register_blueprint(knowledge_bp, url_prefix='/api/v1/knowledge')

    # RAG 问答 API(Sprint 4 - v0.6.0,前缀 /api/v1/rag)
    # 提供 POST /api/v1/rag/query 检索增强问答
    from app.knowledge.api.routes import rag_bp
    app.register_blueprint(rag_bp, url_prefix='/api/v1/rag')

    # 合同审核报告 API(Sprint 5 - v0.7.0,前缀 /api/v1/reviews)
    # 提供 GET /api/v1/reviews/{id} 审核报告查询
    # 注:POST /api/v1/contracts/{id}/review 与 GET /api/v1/contracts/{id}/reviews
    #    已在 contract_api_bp 中注册(资源嵌套于合同)
    from app.api.review.routes import review_bp
    app.register_blueprint(review_bp, url_prefix='/api/v1/reviews')

    # 合同模板管理 API(Sprint 6 - v0.8.0,前缀 /api/v1/templates)
    # 提供 上传 / 列表 / 详情 / 启停 / 删除 模板
    from app.api.templates.routes import template_bp
    app.register_blueprint(template_bp, url_prefix='/api/v1/templates')

    # 合同生成 API(Sprint 6 - v0.8.0,前缀 /api/v1/generation)
    # 提供 预览 / 生成 / 历史列表 / 详情 / Trace
    from app.api.generation.routes import generation_bp
    app.register_blueprint(generation_bp, url_prefix='/api/v1/generation')

    # 生成文件下载 API(Sprint 6 - v0.8.0,前缀 /api/v1/generated)
    # 提供 GET /api/v1/generated/{id}/download Word 文件下载
    from app.api.generation.routes import generated_download_bp
    app.register_blueprint(generated_download_bp, url_prefix='/api/v1/generated')

    # 招标文件管理 API(Sprint 7 - v0.9.0,前缀 /api/v1/bids)
    # 提供 上传 / 列表 / 详情 / 删除 / 重新解析 / 需求查询 / 生成投标
    from app.api.bid.routes import bid_bp
    app.register_blueprint(bid_bp, url_prefix='/api/v1/bids')

    # 投标生成记录 API(Sprint 7 - v0.9.0,前缀 /api/v1/proposals)
    # 提供 列表 / 详情 / Trace / 下载
    from app.api.bid.routes import proposal_bp
    app.register_blueprint(proposal_bp, url_prefix='/api/v1/proposals')

    # ---------- Sprint 8 - v1.0.0 企业级能力新增蓝图 ----------
    # 系统日志 API(Sprint 8:对应 API_DESIGN §10 /api/v1/logs)
    # 提供 GET /logs/operations /logs/ai 分页查询 + ID 详情(仅 admin)
    from app.api.log import log_bp
    app.register_blueprint(log_bp)

    # Prompt 模板管理 API(Sprint 8 /api/v1/prompts)
    # 提供 CRUD + 激活切换(admin),支持 DB active Prompt 替换 .md 文件(DB 不可用时自动回退 .md)
    from app.api.prompt import prompt_bp
    app.register_blueprint(prompt_bp)

    # AI 评估报告 API(Sprint 8 /api/v1/evaluation)
    # 提供 即时评估报告(GET/POST)、历史快照列表和详情(仅 admin)
    from app.api.evaluation import evaluation_bp
    app.register_blueprint(evaluation_bp)

    # 记录启动日志
    from app.extensions.logger import logger
    logger.info('Flask 应用启动完成 | ENV=%s | DEBUG=%s',
                app.config.get('ENV'), app.config.get('DEBUG'))

    return app
