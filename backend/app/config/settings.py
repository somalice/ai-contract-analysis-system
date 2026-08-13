"""
应用配置模块
集中管理 Flask 配置与 DeepSeek 配置。

约束:
- 所有敏感信息从 .env 读取。
- 默认值与 legacy/app.py 硬编码值完全一致,保证迁移后行为不变。
"""
import os
from dotenv import load_dotenv

# 加载 backend/.env(若存在)
load_dotenv()


class Config:
    """基础配置"""

    # ---------- Flask ----------
    # 默认值与 legacy 'supersecretkey' 一致;生产应通过 .env 覆盖
    SECRET_KEY = os.getenv('SECRET_KEY', 'supersecretkey')

    # ---------- 文件上传 ----------
    # 解析为 backend/uploads 绝对路径,避免 CWD 漂移
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    UPLOAD_FOLDER = os.path.join(_BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    # ---------- DeepSeek ----------
    # 默认值与 legacy 硬编码一致
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
    DEEPSEEK_API_BASE = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com/v1')
    DEEPSEEK_MODEL = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')

    # ---------- Agent Observability(Sprint 5 Final - v0.7.1)----------
    # Agent ReAct 循环最大迭代次数(防无限循环;默认 5)
    MAX_AGENT_ITERATIONS = int(os.getenv('MAX_AGENT_ITERATIONS', '5'))
    # Sprint 8.8 Phase 5: LLM 超时拆分为 connect / read 两段
    # - connect: TCP+TLS 建立连接超时(快速失败,默认 5s)
    # - read: 首字节到完整响应超时(DeepSeek 生成慢时最多等 20s)
    # 兼容:LLM_TIMEOUT 保留为 read 超时的单值入口(旧 .env 无需改动)
    LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', '20'))
    LLM_CONNECT_TIMEOUT = float(os.getenv('LLM_CONNECT_TIMEOUT', '5'))
    LLM_READ_TIMEOUT = float(os.getenv('LLM_READ_TIMEOUT', '20'))
    # LLM 最大 token 输出(决策 JSON 控制在合理范围)
    LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS', '2000'))
    # Sprint 8.8 Phase 6: RAG 回答输出上限独立配置(100-200字回答+精简依据≈600 tokens)
    # 比 agent 的 2000 更紧,压缩生成量 → 降低单次 RAG 调用延迟(P95 < 10s 目标)
    LLM_RAG_MAX_TOKENS = int(os.getenv('LLM_RAG_MAX_TOKENS', '768'))

    # ---------- 数据库(Sprint 0 Release:仅初始化,不建表)----------
    # 默认 SQLite(本地文件);Sprint 1 起可改 MySQL
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'SQLALCHEMY_DATABASE_URI',
        'sqlite:///' + os.path.join(_BASE_DIR, 'instance', 'app.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # 生产关闭 SQL 回显

    # ---------- 日志 ----------
    LOG_DIR = os.path.join(_BASE_DIR, 'logs')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # ---------- CORS(Sprint 2 - v0.4.0 前端 Admin Console)----------
    # 逗号分隔的允许 Origin 列表;禁止使用 "*"(生产安全)
    # 开发默认允许 Vite dev server 的两个地址
    CORS_ORIGINS = os.getenv(
        'CORS_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173'
    )

    # ---------- Embedding & Vector Store(Sprint 4 - v0.6.0 知识库 / RAG)----------
    # Embedding 模型(sentence-transformers;禁止 OpenAI Embedding)
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-small-zh-v1.5')
    # 向量库存储目录:相对 backend 目录的路径解析为绝对路径
    VECTOR_STORE_DIR = os.getenv(
        'VECTOR_STORE_DIR',
        os.path.join(_BASE_DIR, 'storage', 'vectorstore')
    )
    # FAISS 索引文件名
    VECTOR_INDEX_NAME = os.getenv('VECTOR_INDEX_NAME', 'knowledge.faiss')
    # 检索 TopK
    RETRIEVER_TOP_K = int(os.getenv('RETRIEVER_TOP_K', '5'))
    # 检索相似度阈值(归一化余弦)
    RETRIEVER_SCORE_THRESHOLD = float(os.getenv('RETRIEVER_SCORE_THRESHOLD', '0.35'))

    # ---------- Sprint 8.6: RAG 质量优化 ----------
    # Rerank 开关(默认开启;失败自动降级原顺序,不阻断业务)
    RERANK_ENABLED = os.getenv('RERANK_ENABLED', 'true').lower() not in ('0', 'false', 'no', 'off')
    # Reranker 模型(复用 sentence_transformers CrossEncoder,不新增依赖)
    RERANKER_MODEL = os.getenv('RERANKER_MODEL', 'BAAI/bge-reranker-base')
    # Rerank 召回阶段 TopK(FAISS 先召回 N 条供 reranker 重排)
    RERANK_RECALL_K = int(os.getenv('RERANK_RECALL_K', '15'))
    # Rerank 最终返回条数(进入 LLM 的 context 数)
    RERANK_FINAL_TOP_K = int(os.getenv('RERANK_FINAL_TOP_K', '5'))
    # Chunker 模式: semantic(原行为) | contract(强制合同切分) | auto(自动检测)
    CHUNKER_MODE = os.getenv('CHUNKER_MODE', 'auto')
    # Contract chunker 自动检测阈值(auto 模式下命中结构正则数 >= 此值才用合同切分)
    CONTRACT_CHUNKER_AUTO_THRESHOLD = int(os.getenv('CONTRACT_CHUNKER_AUTO_THRESHOLD', '3'))
    # ---------- Sprint 8.8: Contract-aware Chunk 策略(实验驱动优化) ----------
    # 合同 Chunk 大小(字符;超长条款按句二次切分)
    CONTRACT_CHUNK_SIZE = int(os.getenv('CONTRACT_CHUNK_SIZE', '800'))
    # 合同 Chunk overlap(字符;仅对超长条款二次切分生效)
    CONTRACT_CHUNK_OVERLAP = int(os.getenv('CONTRACT_CHUNK_OVERLAP', '0'))
    # 是否在 chunk 文本前置上下文前缀(文档标题 + 条款标题),增强 embedding/检索/LLM 依据
    CONTRACT_CHUNK_INCLUDE_TITLE = os.getenv('CONTRACT_CHUNK_INCLUDE_TITLE', 'true').lower() not in ('0', 'false', 'no', 'off')
    # 条款分组模式:将连续条款合并为 ~chunk_size 的上下文窗口(保留各条款标题作内联小标题)
    CONTRACT_CHUNK_GROUP_CLAUSES = os.getenv('CONTRACT_CHUNK_GROUP_CLAUSES', 'false').lower() not in ('0', 'false', 'no', 'off')
    # LLM 重试次数(仅对 timeout/rate_limit/server_error/network 重试)
    # Sprint 8.8 Phase 5: 从 2 降为 1(重试总次数封顶,避免多轮重试放大 P95)
    LLM_MAX_RETRIES = int(os.getenv('LLM_MAX_RETRIES', '1'))
    # 评估 Answer 生成模式: context_extract(从 context 抽相关句) | llm(真实 LLM) | ground_truth(原行为)
    ANSWER_MODE = os.getenv('ANSWER_MODE', 'context_extract')

    # ---------- Sprint 8.9: RAG Answer 质量优化(Sprint 8.8 后,生成质量阶段) ----------
    # RAG context 压缩开关: true 时在 LLM 生成前用 LLM 对 context 做 extraction,只保留必要信息
    RAG_CONTEXT_COMPRESS = os.getenv('RAG_CONTEXT_COMPRESS', 'false').lower() not in ('0', 'false', 'no', 'off')
    # 同文档相邻 chunk 合并: true 时同一文档 chunk_index 相邻的 chunk 拼接为一条 context(消除条款截断)
    RAG_CONTEXT_MERGE_ADJACENT = os.getenv('RAG_CONTEXT_MERGE_ADJACENT', 'false').lower() not in ('0', 'false', 'no', 'off')
    # Answer Prompt 文件覆盖: 指定 prompts/ 下的文件名(如 rag_answer_v3.md)用于 A/B 实验;
    # 默认空 → 走 DB active 模板 / rag_answer.md
    RAG_ANSWER_PROMPT_FILE = os.getenv('RAG_ANSWER_PROMPT_FILE', '')
    # RAG Answer 生成模式: generate(LLM 生成,默认) | extract(embedding 句级抽取)
    # extract 模式: 对 context 逐句做 embedding 语义检索,取与问题最相关的 top_n 原文完整句子
    # 作为回答。回答句子 100% 逐字来自检索上下文 → Faithfulness 不受 LLM 改写影响;
    # 零额外 LLM 调用 / 零 Token 成本。
    RAG_ANSWER_MODE = os.getenv('RAG_ANSWER_MODE', 'generate')
    # extract 模式参数: 抽取句数上限 / 最低语义相似度(低于视为 context 与问题无关)
    RAG_EXTRACT_TOP_N = int(os.getenv('RAG_EXTRACT_TOP_N', '3'))
    RAG_EXTRACT_MIN_SIM = float(os.getenv('RAG_EXTRACT_MIN_SIM', '0.55'))

    # ---------- Sprint 8.7: RAG 评估性能优化 ----------
    # 评估并行 worker 数(ThreadPoolExecutor;设为 1 则串行,完全回退旧行为)。
    # 实测(CPU 推理 bge-small-zh-v1.5):workers=4 最优(20s/10题),workers=8 反而
    # 因 torch 内部线程竞争降至 50s+,故默认 4,可通过 .env EVALUATION_WORKERS 调整。
    EVALUATION_WORKERS = int(os.getenv('EVALUATION_WORKERS', '4'))
    # 评估缓存总开关(context cache + embedding cache;false=完全禁用)
    EVALUATION_CACHE_ENABLED = os.getenv('EVALUATION_CACHE_ENABLED', 'true').lower() not in ('0', 'false', 'no', 'off')

    # ---------- JWT(Sprint 1 - v0.3.0)----------
    # 从 .env 读取,禁止硬编码生产密钥;默认占位值仅用于开发
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'dev-jwt-secret-change-me-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', '86400'))  # 默认 24 小时(秒)
    JWT_TOKEN_LOCATION = ['headers']
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # ---------- Redis 缓存(Sprint 8 - v1.0.0 企业级 AI 增强)----------
    # 连接串:redis://:password@localhost:6379/0 或 redis://localhost:6379/0
    # 未配置时自动降级为内存字典缓存,不影响业务
    REDIS_URL = os.getenv('REDIS_URL', '')
    # 总开关:false=禁用 Redis,直接走内存降级(便于调试)
    _cache_enabled = os.getenv('CACHE_ENABLED', 'true').lower()
    CACHE_ENABLED = _cache_enabled not in ('0', 'false', 'no', 'off')
    # RAG 查询结果缓存时长(秒),相同问题命中后跳过检索+LLM
    CACHE_TTL_RAG = int(os.getenv('CACHE_TTL_RAG', '3600'))
    # Agent 审核结果缓存时长(秒),5min 内重复审核读缓存
    CACHE_TTL_REVIEW = int(os.getenv('CACHE_TTL_REVIEW', '300'))


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    ENV = 'production'


_CONFIG_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}


def get_config():
    """根据 FLASK_ENV 返回对应配置类,默认开发环境"""
    env = os.getenv('FLASK_ENV', 'development')
    return _CONFIG_MAP.get(env, DevelopmentConfig)
