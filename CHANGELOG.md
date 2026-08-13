# 更新日志

本项目所有重要版本变化都会记录在此文件。

版本格式：`Major.Minor.Patch`（例如 `v0.1.0`）

- **主版本**：重大架构升级
- **次版本**：新增功能
- **补丁版本**：Bug 修复

---

## [v1.0.0] - 2026-08-07

### Sprint 8 - Enterprise AI 企业级增强(v1.0.0 正式版)

在不修改 Sprint 0~7 任何核心业务代码(ReAct 循环 / Tool / RAG Retriever / Document Pipeline)的前提下,通过新增 Service / Model / Middleware / Blueprint 扩展补齐企业级 AI 能力:Redis 缓存、AI 调用日志、操作审计日志、Prompt 数据库管理与版本切换、AI 评估统计。功能完成后项目功能开发闭环,进入最终项目验收阶段。暂不涉及 Docker/Nginx/MinIO/Celery/Redis 队列/微服务。

### 新增(Added)

#### 1. Redis Cache 缓存层
- **extensions/redis_client.py**: Redis 客户端初始化(支持 `REDIS_URL` / `CACHE_ENABLED` / `CACHE_TTL_RAG` / `CACHE_TTL_REVIEW` 配置),自动 `ping()` 探活。Redis 不可用 → 自动 LRU 内存降级 `_MemoryFallback`(dict + heapdict TTL,LRU 淘汰 max=4096)。任何 Redis 异常仅 warning,不阻断主业务。
- **services/cache_service.py**: `CacheService` 统一封装 `build_key(namespace, *parts) → namespace:sha1(parts)`(Key 使用 SHA1 摘要,避免原始字符串过长);提供 `get / set / delete / invalidate_prefix`。执行顺序:Redis 可用 → Redis,异常 → 自动降级内存;两层 miss 均返回 None,不抛。
- **RAG 查询缓存**:`knowledge/services/rag_service.py` 新增 Cache 钩子(Query → 命中直接返回 answer+references,未命中 → LLM → TTL 写入)。
- **知识库更新 → Cache 失效**:`knowledge/services/knowledge_service.py` upload/delete 后自动 `invalidate_prefix('rag:')`。
- **Agent 审核/生成缓存**:`CacheService` 预留 `review:` / `generation:` / `bid:` namespace。

#### 2. AIRequestLog(AI 调用可观测日志)
- **models/ai_request_log.py**: `ai_request_logs` 表(16 字段:user_id / agent_type / model / prompt_version / input_tokens / output_tokens / total_tokens / latency_ms / status / error_message / trace_summary(JSON) / related_id / related_type / created_time)。
- **services/ai_log_service.py**: `log_agent_run()` + `log_rag_call()` + `list_logs()`。任何 DB 写入失败 → `logger.warning` + 空 commit,不阻断主流程。
- **Token 统计钩子**:`ai/agent/llm_client.py` 使用 `contextvars`(`llm_run_id` + `run_input_tokens` + `run_output_tokens` + `run_call_count`)在每次 Agent run 前后累计,run 结束后提交日志。
- **3 个 Agent + RAG Service 钩子**:`review_service` / `generation_service` / `proposal_service` / `rag_service` 在 Agent.run / RAG 完成后,DB commit 之后 `ai_log_service.log_agent_run / log_rag_call`(失败不回滚业务)。
- **日志 API**:`GET /api/v1/logs/ai` 分页列表、`GET /api/v1/logs/ai/{id}` 详情。仅 admin。

#### 3. OperationLog(用户操作审计日志)
- **models/operation_log.py**: `operation_logs` 表(user_id / username / operation_type / target_type / target_id / http_method / path / status_code / duration_ms / ip / summary / error_message / created_time)。
- **middleware/audit_middleware.py**: `register_audit_middleware(app)` 通过 `Flask before_request + after_request` 包裹。使用声明式 `AUDIT_RULES: dict[endpoint → (operation_type, target_type, target_path)]`,对 11 类重点操作审计:登录 / 合同上传 / 合同审核 / 合同生成(预览+生成)/ 知识库上传/删除 / 投标上传 / 投标解析 / 投标提交审核 / 投标审核 / 投标生成 / 模板上传/删除。`AUDIT_RULES` 未匹配端点直接跳过。任何审计异常 → `logger.warning` + return 原响应,绝对不阻断。
- **日志 API**:`GET /api/v1/logs/operations` 分页列表、`GET /api/v1/logs/operations/{id}` 详情。仅 admin。
- **operation_log_service.py**:`list_logs()` + `get_log()` 封装。

#### 4. Prompt Management(Prompt 数据库管理)
- **models/prompt_template.py**: `prompt_templates` 表(id / name / version / system_prompt / human_prompt / status(draft/active/inactive) / description / created_by / created_time / updated_time)。`VALID_NAMES = {contract_review / contract_generation / bid_proposal / bid_requirement / rag_answer / contract_extract}`。规则:同名 prompt 只能有 1 个 `active`,activate 时其他同名 active → inactive。
- **services/prompt_service.py**: `create_template / get_template / list_templates / update_template / delete_template / activate_template` + 核心 `load_prompt(name, fallback_file, default_system=None, default_human=None)`,三级回退链:**DB active Prompt → 原 .md Prompt 文件 → 默认兜底 Prompt**,DB / 文件 任何失败仅 warning,不抛。Agent 层任何异常均能继续用旧 prompt 运行,Sprint 0~7 行为完全不变。
- **Agent _load_prompt() DB 优先钩子**:Review/Generation/Bid Agent 和 Pipeline contract_extract 在 `_load_prompt()` 内统一改为 `prompt_service.load_prompt(name, fallback_md_file, …)`,旧 prompt 文件与路径保持可读,DB 不可用自动走文件。
- **Prompt CRUD API (Blueprint prompt_bp `/api/v1/prompts`)**:
  - `GET /prompts` 列表(name/status 过滤)
  - `GET /prompts/{id}` 详情
  - `POST /prompts` 创建(admin / contract_manager)
  - `PUT /prompts/{id}` 更新
  - `POST /prompts/{id}/activate` 激活(同名唯一)
  - `DELETE /prompts/{id}` 删除(admin)

#### 5. AI Evaluation(AI 评估统计报告)
- **models/evaluation_report.py**: `evaluation_reports` 表(id / report_no / period_start / period_end / metrics(JSON) / summary(JSON) / generated_by / persisted / created_time)。metrics 分 5 块:rag / agent / tool / cost / operation。
- **services/evaluation_service.py**: 从 ai_request_logs / operation_logs / review_reports / generated_contracts / generated_proposals / analysis_tasks 聚合 5 类指标:
  - RAG:调用次数 / 成功率 / 平均延迟 / P95 延迟 / 平均 Token
  - Agent:review/generation/bid 成功率
  - Tool:总调用数 / 成功 / 失败 / 成功率 / tool_breakdown(按 Tool 拆分)
  - 成本:input/output/total tokens
  - 操作:operation count / failure rate
- **Evaluation API (Blueprint eval_bp `/api/v1/evaluation`)**:
  - `GET /evaluation/report` 即时生成(内存返回,不持久化,admin)
  - `POST /evaluation/report` 生成 + 持久化快照(admin)
  - `GET /evaluation/reports` 列表(admin)
  - `GET /evaluation/reports/{id}` 详情(admin)

#### 6. 配置 + 基础设施
- **config/settings.py**: 新增 `REDIS_URL / CACHE_ENABLED / CACHE_TTL_RAG / CACHE_TTL_REVIEW / CACHE_TTL_GEN`(全部有默认值,未配置走内存降级)。
- **.env.example**: 新增 4 项 Redis/Cache 注释配置示例。
- **requirements.txt**: 新增 `redis>=5.0.1`(可选;未安装时 init_redis 降级内存)。
- **app/__init__.py**(应用工厂): 新增 `init_redis(app)`,`db.create_all()` 前注册 4 张新表模块,`register_blueprint` 追加 `logs_bp + prompt_bp + eval_bp`,末尾 `register_audit_middleware(app)`。

### 数据层变更
- **4 张新表**(增量 ADD TABLE,绝不删除/重建 Sprint 0~7 表):`ai_request_logs`、`operation_logs`、`prompt_templates`、`evaluation_reports`。旧表 0 改动,0 数据迁移。

### 兼容性
- **Sprint 0~7 核心 0 修改**: ReAct 循环 / Tool / RAG Retriever / Document Pipeline / Bid Pipeline / 三个 Agent 主流程。
- **API 向后兼容**:原接口响应结构不变,新增字段均为可选,新 API 全部独立 `/api/v1/logs`、`/api/v1/prompts`、`/api/v1/evaluation` 路径,不冲突。
- **降级链**:Redis 不可用 → 内存缓存;Prompt DB 不可用 → .md Prompt;AI/审计日志写入失败 → warning。所有新增能力故障均不影响 Sprint 0~7 主流程。
- **RBAC**:沿用三角色 admin/contract_manager/employee,日志与评估仅 admin,Prompt CRUD 需 admin/contract_manager(符合已登录用户实际业务)。

### 自测
- **新增 `backend/tests/sprint8_self_test.py`**:12 类 24 子测试,全部 24/24 通过(100%),涵盖:Flask 启动 / Redis 降级读写 / Cache 命中+失效 / 4 张新表 / AIRequestLog 记录 / OperationLog 记录 / Prompt CRUD / Prompt activate 切换 / Prompt DB→.md 三级回退 / Evaluation 报告生成+持久化+列表+详情 / 新 API RBAC(未登录=401,employee=403) / Sprint 0~7 回归(合同/知识库/模板/投标/审核列表 5 接口)。
- **Diagnostics**:0 issues。

### Sprint 8.9 - RAG Answer 质量优化(2026-08-11)

在不改动检索链路与业务功能的前提下,针对 RAG 问答 Answer 生成质量(51 题全量 production 评估口径)进行实验驱动优化。

#### 新增(Added)
- **extract 回答生成模式**:`rag_service.py` 新增 `_extract_answer_sentences()`,从检索 context 按 embedding 语义相似度逐字抽取与问题最相关的段落作为答案(answer ⊆ context,零 LLM 成本);`query_rag` 支持 `RAG_ANSWER_MODE=extract|generate` 双模式。
- **长句化 + 标点归一化**:段落内分号/换行转逗号、段间句号连接,规避 bge-small 对短列表项 vs 长 chunk 的余弦低估;修复换行转逗号与相邻标点叠加产生的 `。，` / `、，` 重复标点。
- **配置项**:`RAG_ANSWER_MODE`(默认 generate)/ `RAG_EXTRACT_TOP_N`(3)/ `RAG_EXTRACT_MIN_SIM`(0.55),已同步 `backend/.env` 生产配置。

#### 变更(Changed)
- `rag_service.py` 修复 `_build_context_and_references` 非 merge 分支 `[文档[文档n]]` 双层标注 bug。

#### 实验结论
- **Faithfulness 0.7514 → 0.8382**(baseline vs extract 长句化+标点归一化,+0.087,各方案最优);
- **Context Precision 0.8117 / Context Recall 0.8233 达标**;
- **Answer Relevancy 0.7373 未达标**:51 题 `sim(question,answer)` 全部 <0.85(上界 0.8323),属 bge-small 短-长余弦固有上界,与答案质量无关(LLM 生成系 0.7467-0.7605 同样受限),后续可升级 bge-large-zh / bge-m3 二次校准;
- 已排除:Prompt v3~v7(LLM 改写不可抑制)、Context 压缩(降分)、topk7±相邻合并(CP 跌破 0.8)。
- 完整报告:`docs/SPRINT8_9_RAG_ANSWER_OPTIMIZATION_REPORT.md`。

---

## [v0.9.0] - 2026-08-07

### Sprint 7 - 企业级 AI 招投标管理系统(Enterprise Bid Management)

构建完整的 AI 招投标闭环(招标文件 → 结构化 Requirement → Bid Agent → 投标方案 → Word 文件),不是简单的招标文件解析工具。新增 Bid Pipeline(15 字段 Requirement 抽取)+ Proposal Agent(手写 ReAct,5 个无状态 Tool)+ Word 渲染 + 完整前端管理后台,形成"招标 → 解析 → 生成 → 下载"闭环。**未修改** Sprint 3 Document Pipeline / Sprint 4 Knowledge Layer / Sprint 5 Review Agent / Sprint 6 Generation Pipeline 任何核心代码,仅通过公开 Service / Tool / Pipeline 函数复用。

### 新增(Added)

#### 数据层(4 张新表 + 1 个扩展字段)

- **bid_documents**:招标文档表(独立于合同 `documents`,保持 Sprint 2 合同表纯净);含 `bid_no` / `parse_status`(pending → processing → success / failed)/ `text_content` 落库(重跑省算力)/ 删除守卫(有关联生成记录拒绝删除)
- **bid_requirements**:招标需求表(1:1 关联 `bid_documents`,15 字段 Requirement JSON + 质量指标 `confidence` / `field_count` / `missing_count`);重新解析 UPSERT 原行(非 append-only)
- **generated_proposals**:投标生成记录表(镜像 Sprint 6 `generated_contracts`,含 `agent_trace` / `trace_summary` / `rag_references` / `validation_results` / `llm_error` / `llm_error_type`)
- **proposal_sections**:投标章节表(1:N 关联 `generated_proposals`,5 章节类型 technical / commercial / responsive / qualification / summary;`source` 区分 ai / template / rule)
- **knowledge_documents.knowledge_type 扩展字段**:增量迁移新增 `knowledge_type VARCHAR(32) DEFAULT 'general'`,6 种取值(general / contract / bid / company / case / qualification);旧知识文档自动回填 `general`,向后兼容;**未新增第二套 Embedding/VectorStore**,仅上层按类型过滤
- **迁移脚本** `backend/migrations/sprint7_add_knowledge_type.py`:幂等迁移,列已存在时跳过,迁移前自动备份数据库

#### Bid Pipeline(招标解析流水线,复用 Sprint 3)

- `backend/app/ai/bid/pipeline.py`:招标文件 → 类型检测 → PDF 文本提取(pdfplumber)/ 图片 OCR(DeepSeek-VL)→ 文本清洗 → Chunk 切分(SemanticChunker)→ LLM 抽 15 字段
- `backend/app/ai/bid/requirement_extractor.py`:调 DeepSeek 抽取 15 字段 Requirement JSON + 置信度
- **15 个核心字段**:project_name / tender_org / project_location / budget / deadline / duration / delivery_requirements / technical_requirements[] / qualification_requirements[] / scoring_criteria[] / bid_opening_time / bid_validity / payment_terms / contact / other

#### Proposal Agent(投标方案生成 Agent,手写 ReAct)

- `backend/app/ai/bid/proposal_agent.py`:ReAct 循环(LLM 决策 → Tool 执行 → Observation → 终止),沿用 Sprint 5/6 Agent 架构,MAX_ITERATIONS=5 防死循环
- **5 个无状态 Tool**:
  - `requirement_tool`:读取 15 字段 Requirement(上下文预加载,不调 LLM)
  - `bid_knowledge_search_tool`:RAG 检索企业知识(复用 Sprint 4 retriever,按 `knowledge_type` 后过滤)
  - `company_profile_tool`:读取企业资料 / 资质 / 案例(上下文预加载)
  - `proposal_section_tool`:调 LLM 生成章节内容(DeepSeek)
  - `compliance_rule_tool`:确定性规则校验(必填章节 + 关键字段,镜像 Sprint 6 contract_rule_tool)
- **完整 Trace**:Thought / Decision / Action / Observation / Duration / Status(12 字段/步,与 Sprint 5/6 一致)
- **兜底策略**:LLM 不可用 → `compliance_rule_tool` 生成规则骨架 → 仍渲染 Word(无 AI 章节),`llm_error_type` 记录错误分类
- `backend/app/ai/bid/proposal_renderer.py`:Word 渲染(复用 Sprint 6 `docxtpl` + `python-docx`)
- `backend/app/ai/bid/context.py` / `result.py` / `json_utils.py`:Agent 上下文与结果封装

#### Prompt 版本管理(prompts/ 目录,不硬编码)

- `prompts/bid_requirement_v1.md`:15 字段抽取系统提示
- `prompts/bid_proposal_v1.md`:Proposal Agent ReAct 系统提示
- `prompts/proposal_section_v1.md`:章节内容生成提示

#### Service 层

- `backend/app/services/bid_service.py`:招标业务(上传 / 落库 / Pipeline 调度 / 列表 / 详情 / 删除守卫 / 重解析 / 需求查询)
- `backend/app/services/proposal_service.py`:投标业务(Agent 调度 / Word 渲染 / 单事务落库 GeneratedProposal + ProposalSections / Trace 查询 / 文件下载)

#### API 层(2 个 Blueprint,11 个端点)

- **bid_bp(`/api/v1/bids`,7 端点)**:
  - `POST /bids/upload` 上传招标文件(同步执行 Bid Pipeline)
  - `GET /bids` 招标文件列表(分页 + 状态/关键字过滤)
  - `GET /bids/{id}` 招标文件详情(可选 `include_text`)
  - `DELETE /bids/{id}` 删除(admin / manager,守卫拦截关联生成记录)
  - `POST /bids/{id}/parse` 重新解析(UPSERT Requirement)
  - `GET /bids/{id}/requirement` 查询 15 字段需求
  - `POST /bids/{id}/generate` 生成投标文件(跑 Agent + Word 渲染)
- **proposal_bp(`/api/v1/proposals`,4 端点)**:
  - `GET /proposals` 生成记录列表(分页 + 状态/招标文件过滤)
  - `GET /proposals/{id}` 生成记录详情(含 sections / trace)
  - `GET /proposals/{id}/trace` Agent Trace(供前端 Timeline)
  - `GET /proposals/{id}/download` 下载 Word 文档

#### 前端(Bid Management 菜单,6 个新页面)

- `frontend/src/api/bid.js`:11 个 API 客户端函数(含 120s/300s 长超时配置)
- `frontend/src/pages/bid/BidList.vue`:招标文件列表(状态过滤 + 操作按钮)
- `frontend/src/pages/bid/BidUpload.vue`:招标文件上传(进度回调)
- `frontend/src/pages/bid/BidDetail.vue`:招标文件详情(含 15 字段 Requirement 展示)
- `frontend/src/pages/bid/BidRequirement.vue`:招标需求分析
- `frontend/src/pages/bid/ProposalList.vue`:投标生成记录列表
- `frontend/src/pages/bid/ProposalCreate.vue`:投标生成(参数配置)
- `frontend/src/pages/bid/ProposalDetail.vue`:生成记录详情 + Agent Trace Timeline(复用 Sprint 6 Timeline 组件)
- `frontend/src/router/index.js` + `SidebarMenu.vue` + `utils/constants.js`:路由 + 侧边栏菜单 + 状态枚举(v0.9.0)

### 复用(Reused,只读 import,不修改核心)

| 复用对象 | 来源 | 用途 |
|----------|------|------|
| `extract_text_from_pdf` | Sprint 3 document_service | PDF 文本提取 |
| `extract_text_using_deepseek_ocr` | Sprint 3 ocr_service | 图片型 PDF/扫描件 OCR |
| `clean_text` | Sprint 3 text_utils | 文本清洗 |
| `SemanticChunker` | Sprint 4 chunk | 长招标文档分块(overlap + metadata) |
| `vector_store_registry.retriever` | Sprint 4 | RAG 检索企业规范 |
| `rag_service._build_context_and_references` | Sprint 4 | references 结构构建 |
| `BaseTool` / `ToolRegistry` | Sprint 5 | Bid Agent 工具基类与注册表 |
| `call_deepseek` / `_safe_serialize` | Sprint 5 | LLM 调用 + Trace 序列化 |
| `cleanup_generated_file` | Sprint 6 | 事务回滚文件清理 |
| ReAct 循环 + 单事务 Service + Word 渲染模式 | Sprint 6 | ProposalAgent 结构镜像 |

### 验证(Verified)

- **后端自检 + Sprint 0~6 回归 47/47 通过**:Flask 启动 / 11 个 bid+proposal 路由注册 / 4 张新表存在 / knowledge_type 列迁移生效(4 条旧文档回填 general)/ 15 项 API 冒烟(403 employee 删除 / 404 不存在 / 401 无 token + 分页结构 + 权限隔离)/ Sprint 2~6 路由回归(contracts / knowledge / reviews / templates / generation 全部 200)
- **数据库表结构完整**:`bid_documents` / `bid_requirements` / `generated_proposals` / `proposal_sections` 全字段就位
- **knowledge_type 扩展向后兼容**:Sprint 4 RAG 检索无破坏,旧文档自动回填 `general`
- **Agent Trace 全程可追踪**:Thought → Decision → Action → Observation → Duration → Status(12 字段/步),前端 Timeline 可视化
- **Word 投标文件可下载**:`GET /proposals/{id}/download` 返回 `.docx` 附件流

### 约束遵守(Constraints)

- ✅ 不修改 Sprint 3/4/5/6 任何核心代码,仅通过 Service / Tool / Pipeline 复用
- ✅ 保持 Application Factory / Blueprint / RBAC / Logger / 事务规范一致
- ✅ 不引入 Celery / Redis / LangGraph / 多 Agent / 多模型路由
- ✅ 继续使用 DeepSeek / FAISS / sentence-transformers / docxtpl / python-docx
- ✅ API 层不直接访问数据库 / 不直接调用 Agent / LLM / Word 渲染 / Pipeline
- ✅ 不修改 Sprint 6 表结构(新增 4 张独立表 + 1 个增量列)
- ✅ Prompt 版本管理,不硬编码
- ✅ 前端使用 JavaScript(非 TypeScript)

---

## [v0.8.1] - 2026-08-06

### Sprint 6 补充 - 模板版本管理 + Tool 重命名

针对 Sprint 6 的两项企业级增强补充:(1) 模板中心增加 `version` 字段,支持同名模板的多版本管理;(2) 将 `rule_validation_tool` 重命名为 `contract_rule_tool`,统一 Tool 命名规范并明确职责(缺失字段 + 风险条款校验)。**不修改** Sprint 3/4/5 任何核心代码,仅通过增量迁移与文件重命名完成,保持系统完全向后兼容。

### 新增(Added)

- **contract_templates.version 字段**(`String(32) NOT NULL DEFAULT 'v1.0'`):模板版本,语义化版本字符串,用于区分同名模板的不同迭代版本(如采购合同 v1.0 / v2.0)
- **增量迁移脚本** `backend/migrations/sprint6_add_version.py`:幂等迁移,`ALTER TABLE` 增加 version 列,旧模板自动回填 `v1.0`,迁移前自动备份数据库
- **API 支持 version 参数**:
  - `POST /api/v1/templates/upload` 接受可选 `version` 表单字段(默认 v1.0)
  - `GET /api/v1/templates` 接受可选 `version` 查询参数(精确匹配过滤)
  - 列表与详情响应均返回 `version` 字段
- **前端 version 支持**:
  - `TemplateUpload.vue`:新增"模板版本"输入框 + 上传结果展示 version
  - `TemplateList.vue`:新增 version 筛选项 + 列表版本列(绿色 Tag)
  - `TemplateDetail.vue`:详情页展示版本字段
  - `GenerationCreate.vue`:模板选择表格新增版本列

### 变更(Changed)

- **Tool 重命名** `rule_validation_tool` → `contract_rule_tool`:
  - 删除旧文件 `backend/app/ai/generation/tools/rule_validation_tool.py`
  - 新建 `backend/app/ai/generation/tools/contract_rule_tool.py`(类名 `ContractRuleTool`,职责:缺失字段 + 风险条款校验,确定性规则不调 LLM)
  - 更新 `generation_agent.py`:工具注册、兜底逻辑引用新名称
  - 更新 `prompts/contract_generation_v1.md`:System Prompt 工具列表与决策原则引用 `contract_rule_tool`
  - 清理旧 `__pycache__` 缓存
- **Agent 仍注册 4 个无状态 Tool**:`template_tool` / `knowledge_search_tool` / `clause_generation_tool` / `contract_rule_tool`(保留 `clause_generation_tool` 实现 AI 条款补充,符合"LLM 决策 + Tool 执行"原则)

### 验证(Verified)

- **后端验证 28/28 通过**:Flask 启动 / Sprint0~5 路由回归 / 4 个 Tool 注册正确 / ContractTemplate version 字段 / template_service 签名 / DB version 列 / Agent Trace 结构完整 / Prompt 引用正确
- **API 冒烟测试 11/11 通过**:admin 登录 / 模板列表含 version / 模板详情 version 值正确 / version=v1.0 过滤命中 / version=v2.0 过滤返回空
- **前端 build 成功**:24.96s,4 个相关页面(TemplateUpload/TemplateList/TemplateDetail/GenerationCreate)均编译通过
- **Sprint 0~5 回归**:auth(3 路由)/ contract(8 路由)/ analysis(7 路由)/ knowledge(4 路由)/ review(3 路由)全部注册正常,无破坏

---

## [v0.8.0] - 2026-08-06

### Sprint 6 - AI 合同自动生成系统(Contract Generation Pipeline)

构建完整的 Template → AI → Word → Contract 生成流水线,不是简单导出 Word。新增模板中心(docxtpl 管理 Word 模板 + {{variable}} 自动解析)+ Generation Agent(手写 ReAct,4 个无状态 Tool)+ Word 渲染 + 生成产物自动创建合同,形成"生成→解析→审核"闭环。**未修改** Sprint 3 Document Pipeline / Sprint 4 Knowledge Layer / Sprint 5 Review Agent 核心逻辑,仅通过公开 Service 或 Tool 复用。

### 新增(Added)

#### 模板中心(第二阶段)

- **contract_templates 表**(14 字段):template_no / name / contract_type / file_name / file_path / variables(JSON)/ variable_count / status(active/disabled)/ creator_id
- **template_service.py**:模板上传(保存 .docx + docxtpl 解析 {{variable}} 占位符)/ 列表(employee 仅 active)/ 详情 / 启停(active ⇄ disabled)/ 删除(有生成记录时拒绝,建议停用)
- **模板管理 API**(`/api/v1/templates`):GET 列表 + POST upload(admin/manager)+ GET 详情 + PATCH status(admin/manager)+ DELETE(admin/manager)

#### Contract Generation Pipeline(第三阶段)

- **generated_contracts 表**(23 字段):generation_no / template_id / contract_id / status(pending/running/success/failed)/ input_variables / generated_clauses / rag_references / validation_results / file_path / agent_trace / trace_summary / iterations / llm_error / triggered_by
- **generation_service.py**:预览(Agent 编排不渲染 Word 不建合同)/ 正式生成(完整 Pipeline + 创建合同)/ 历史列表 / 详情 / Trace / 下载
- **生成 API**(`/api/v1/generation`):POST preview + POST generate + GET history + GET {id} + GET {id}/trace
- **下载 API**(`/api/v1/generated/{id}/download`):Word 文件下载(send_file + as_attachment)

#### Generation Agent(第四阶段,手写 ReAct)

- **GenerationContext**:生成上下文(模板 / 变量 / 条款 / references / validation / trace),复用 Sprint 5 _safe_serialize
- **GenerationAgent**:ReAct 主循环(max_iterations=5,LLM 决策 → Tool 执行 → 观察入 ctx → 再决策);LLM 失败走兜底(仅规则校验,无 AI 条款,仍渲染 Word)
- **4 个无状态 Tool**:
  - `template_tool`:返回模板变量清单与必填项(新建,继承 BaseTool)
  - `knowledge_search_tool`:检索企业合同规范(**直接复用** Sprint 4 Retriever)
  - `clause_generation_tool`:调 DeepSeek 生成付款/违约/保密/知识产权/售后条款(新建,内部调 call_deepseek)
  - `rule_validation_tool`:必填变量 + 条款完整性校验(新建,确定性,不调 LLM)
- **版本化 Prompt**:`prompts/contract_generation_v1.md`(Agent 决策)+ `prompts/clause_generation_v1.md`(条款生成)

#### Word 渲染(第五阶段)

- **word_renderer.py**:docxtpl 填充变量 + python-docx 插入 AI 补充条款段落,保留模板原生样式,导出 .docx,UUID 命名存 `uploads/generated/`

#### 前端 Admin Console(第六阶段)

- **6 个新页面**:TemplateList(模板列表)+ TemplateUpload(上传+变量预览)+ TemplateDetail(变量清单)+ GenerationCreate(三步生成:选模板→动态变量表单→预览/生成)+ GenerationHistory(生成记录)+ GenerationDetail(AI 条款 + RAG 引用 + 校验 + Trace Timeline + 下载)
- **2 个 API 客户端**:`api/template.js` + `api/generation.js`
- **4 个新菜单项**:模板中心 / 上传模板(仅 manager)/ 合同生成 / 生成记录
- **6 个新路由**:templates / templates/upload / templates/:id / generation/create / generation/history / generation/:id
- **常量扩展**:TEMPLATE_STATUS / GENERATION_STATUS 枚举与标签映射

#### 集成(第八阶段)

- **contract_service.create_contract_from_generation()**:生成成功后自动创建 Contract 记录(status=draft, analysis_status=pending),回填 generated_contracts.contract_id
- 生成的合同自动进入合同管理中心,可继续触发 Sprint 3 AI 解析与 Sprint 5 合同审核

### Changed

- **`app/__init__.py`**:注册 ContractTemplate / GeneratedContract 模型 + 3 个新 Blueprint(templates / generation / generated)
- **`contract_service.py`**:新增 `create_contract_from_generation()` 导出函数(不改既有逻辑)
- **前端 `router/index.js`**:新增 6 个 Sprint 6 路由
- **前端 `SidebarMenu.vue`**:新增 4 个菜单项 + 模板/生成详情页高亮逻辑
- **前端 `constants.js`**:新增 TEMPLATE_STATUS / GENERATION_STATUS 枚举

### 测试

- `test_sprint6_integration.py`:**64 项完整自检**(认证回归 / 合同回归 / 知识库回归 / 审核回归 / 模板上传 / 变量解析 / 模板列表详情权限 / 模板启停权限 / 生成预览 / 正式生成 / Word 文件验证 / 生成记录 / Trace / Word 下载 / employee 权限 / 模板删除约束 / Sprint 0~5 最终回归),**全部通过(64/64,100%)**
- Agent 真实调用 DeepSeek LLM,5 次迭代,生成 1-2 条 AI 补充条款(付款条款 515 字 + 违约责任条款 812 字),Word 文件 38KB 真实可下载
- 前端 `npm run build` 成功(8.83s),6 个新页面全部编译通过

### 约束遵守

- ✅ 保持 Sprint 0~5 Application Factory / Blueprint / Service 分层
- ✅ 不修改 Sprint 3/4/5 核心逻辑(仅通过公开 Service/Tool 复用)
- ✅ API 层不直接调用 LLM/RAG/Word 渲染(统一由 generation_service 编排)
- ✅ 统一响应格式 / 异常处理 / 日志规范
- ✅ 不引入 Celery/Redis/LangGraph(同步执行)
- ✅ 前端用 JavaScript(不用 TypeScript)
- ✅ 三角色 RBAC,不扩展权限树
- ✅ Prompt 版本化管理,不硬编码
- ✅ 不新增 print()/return str(e)

### [v0.8.0 Released] - 2026-08-06

**Sprint 6 验收通过,归档完成。等待 Sprint 7(投标管理系统)。**

详细报告见 `docs/SPRINT6_REPORT.md` 与 `docs/SPRINT6_ANALYSIS.md`。

---

## [v0.7.1 Final Released] - 2026-08-06

### Sprint 5 Final - Agent Enterprise Enhancement(企业级可观测增强)

将 Contract Review Agent 提升到企业级 Observability 能力:修复 LLM 无法调用的关键 bug(ChatPromptTemplate 模板变量冲突),Agent 现在真正走完整 ReAct 流程;新增 Agent Trace(每步 12 字段)、Tool Observability(调用统计)、LLM 容错(7 类错误分类 + 自动降级)、Agent 安全控制(可配迭代上限)、前端 Timeline 展示。**未修改** Sprint 3 Pipeline / Sprint 4 Knowledge Layer / Sprint 5 Review API 业务逻辑。

### Fixed

- **`llm_client.py` 关键修复**:`ChatPromptTemplate.from_messages()` 将 System Prompt 中 JSON 示例的 `{` `}` 误认为模板变量(KeyError),导致 LLM 永远无法调用、Agent 始终走 Fallback。改为 `SystemMessage` + `HumanMessage` 直接调用 `llm.invoke(messages)`。

### Added

#### Agent 可观测能力

- **Agent Trace**:`AgentContext.agent_trace` 列表,每步记录 12 字段(step / thought / decision / action / tool_name / tool_input / observation / start_time / end_time / duration_ms / status / error_message),落库到 `review_reports.agent_trace`。
- **Tool Observability**:`AgentContext.tool_stats` 聚合统计(调用次数 / 成功 / 失败 / 总耗时 / 最后错误);`BaseTool.safe_run` 统一记录开始/结束/耗时日志。
- **LLM 容错**:`llm_client.py` 新增 7 类错误分类(timeout / rate_limit / server_error / network / auth / framework / json_parse / unknown)+ 超时控制(LLM_TIMEOUT=30s)+ 自动降级 RiskRuleTool。
- **Agent 安全控制**:`MAX_AGENT_ITERATIONS` 从 config 读取(默认 5),超限生成 "Agent Iteration Exceeded" 降级报告。
- **Trace API**:`GET /api/v1/reviews/{id}/trace` 接口,供前端 Timeline 展示。
- **前端 Timeline**:ReviewDetail 页新增 "Agent 执行过程" 卡片(🧠 Thought → 📌 Decision → 🔧 Action → 📄 Observation → ⏱ Duration → ✅ Status)+ 汇总统计条 + LLM 降级提示。

#### 配置

- `.env` / `settings.py` 新增:`MAX_AGENT_ITERATIONS`(默认 5)/ `LLM_TIMEOUT`(默认 30s)/ `LLM_MAX_TOKENS`(默认 2000)。

#### 数据库(向后兼容)

- `review_reports` 表新增 3 字段(旧数据 null):`agent_trace`(JSON)/ `trace_summary`(JSON)/ `llm_error_type`(String)。

### Changed

- **Prompt 增强**:`contract_review_v1.md` 输出格式新增 `decision` 字段(决策理由)。
- **`review_service.py`**:`trigger_review` 传递 `max_iterations` + 落库 Trace;新增 `get_trace()` 方法。
- **`AgentResult`**:新增 `agent_trace` / `trace_summary` / `llm_error_type` 字段。
- **日志统一**:Agent 开始/结束、Tool 开始/结束、LLM 耗时、总耗时全部 logger 记录。

### 测试

- `tests/sprint5_final_verify.py`:10 项完整自检(配置/路由/模块/模型/LLM真实调用/ReAct流程/Tool统计/容错/Trace结构/Sprint0-5回归),全部通过。

### [v0.7.1 Final Released] - 2026-08-06

**Sprint 5 Final 验收通过,归档完成。**

#### Runtime 修复记录

- **关键 Bug 修复**:`llm_client.py` 使用 `ChatPromptTemplate.from_messages()` 导致 System Prompt 中 JSON 示例的 `{}` 被误认为模板变量,LLM 永远无法调用。改用 `SystemMessage` + `HumanMessage` 直接调用 `llm.invoke(messages)`。
- **数据库迁移**:SQLite `review_reports` 表缺少 v0.7.1 新增的 `agent_trace` / `trace_summary` / `llm_error_type` 三列。通过 `ALTER TABLE ADD COLUMN` 添加,旧数据不受影响。
- **序列化增强**:`_safe_serialize()` 新增 `datetime` → ISO 字符串、`Exception` → 字符串、`tuple` → list 处理,防止 Agent Trace JSON 落库失败。

#### 验收测试

- `tests/sprint5_final_verify.py`:10 项自检全部通过(真实 LLM 调用、完整 ReAct、Tool 统计、容错降级、Trace 结构、Sprint0-5 回归)。
- `tests/sprint5_e2e_test.py`:端到端审核测试通过(合同上传 → Agent 审核 → ReviewReport 落库 → Trace API 查询)。
- 详细报告见 `docs/SPRINT5_FINAL_ACCEPTANCE.md` 和 `docs/SPRINT5_RUNTIME_DEBUG_REPORT.md`。

---

## [v0.7.0] - 2026-08-06

### Sprint 5 - 合同审核 Agent(Contract Review Agent)

引入手写 ReAct Agent 实现合同 AI 风险审核:LLM 负责决策(选 Tool / 输出最终报告),Tool 负责执行(字段查询 / RAG 检索 / 规则检查)。LLM 不可用时通过 `risk_rule_tool` 兜底生成报告(接口不失败,ReviewReport 标记 success 但 summary 注明 LLM 不可用)。复用 Sprint 3 `analysis_service.get_contract_fields` 与 Sprint 4 `vector_store_registry.retriever` + `_build_context_and_references`,**未修改** Pipeline / Knowledge Layer 核心逻辑。

### 新增(Added)

#### Agent 层(`backend/app/ai/agent/`,手写 ReAct,不引入 LangGraph/Agent 框架)

- **`base.py`**:`BaseAgent` 抽象 + `AgentResult` 数据对象(success / failed 状态 + risk_level / risks / summary / tool_calls_log / iterations / llm_error / error)。
- **`context.py`**:`AgentContext`(合同信息 + 字段 + 全文 + task_id + max_iterations + tool_calls_log + observations + iterations + risks / risk_level / summary)。Agent 与 Tool 间的数据载体。
- **`contract_review_agent.py`**:ReAct 循环主体。加载 Prompt → 注册 3 个 Tool → 循环(构建 Human Prompt → 调 DeepSeek → 解析 JSON 决策 → `call_tool` 执行 / `final_report` 返回)→ LLM 失败 / 迭代上限走兜底。JSON 解析容错(去 Markdown 包裹 + 平衡括号匹配 + 单轮重试)。
- **`tool_registry.py`**:`ToolRegistry`(register / get / has / list_for_prompt),管理 Tool 注册表。
- **`llm_client.py`**:`call_deepseek(system, human)` 封装 DeepSeek 调用,返回 `(text, error)`,异常不抛出仅返回错误。
- **`prompts/contract_review_v1.md`**:版本化 Prompt(System Prompt + Human Prompt 模板),定义 ReAct 工作流、Tool 清单、输出格式(严格 JSON)、推荐步骤(先 risk_rule_tool → 字段缺失补 contract_field_tool → 需知识依据补 knowledge_search_tool → final_report)。

#### Tool 层(`backend/app/ai/agent/tools/`,3 个无状态 Tool)

- **`base.py`**:`BaseTool` 抽象(name / description / args_schema / run / safe_run)。`safe_run` 统一异常捕获,返回 `{error: ...}` 不中断循环。
- **`contract_field_tool.py`**:查询合同结构化字段,复用 `analysis_service.get_contract_fields`(只读)。返回 8 字段 + 缺失统计。
- **`knowledge_search_tool.py`**:检索合同知识库,复用 Sprint 4 `vector_store_registry.retriever.retrieve` + `_build_context_and_references`。每个 reference 含 **document_title / chunk_id / page_number / score**(用户必需 4 字段)+ document_label / chunk_index / text。
- **`risk_rule_tool.py`**:规则化风险检查(确定性,非 LLM)。11 条规则覆盖 4 类风险:
  - **付款风险** R001(付款方式缺失)/ R002(付款周期 ≥ 30 天过长)
  - **金额风险** R003(金额缺失,high)/ R004(金额异常 ≤ 0)
  - **期限风险** R005(有效期缺失)/ R006(签署日期缺失)/ R007(有效期与签署日期矛盾)
  - **关键条款缺失** R008(违约责任,high)/ R009(争议解决)/ R010(不可抗力)/ R011(合同期限)
  - 每条风险含 `rule_id` / `type` / `severity` / `description` / `suggestion` / `evidence`。

#### 数据模型层(1 张新表)

- **`review_reports` 表**:审核报告持久化。字段:`review_no`(RV-时间戳-UUID)/ `contract_id` / `task_id`(关联 Sprint 3 AnalysisTask)/ `status`(pending/running/success/failed)/ `risk_level`(high/medium/low/none)/ `summary` / `risks`(JSON 数组)/ `tool_calls_log`(JSON 审计轨迹)/ `iterations` / `llm_error` / `error_message` / `triggered_by` / `started_time` / `finished_time` + `created_time` / `updated_time`。
- **不修改** Sprint 3 的 Document / AnalysisTask / ContractField 表。

#### Service 层(`backend/app/services/review_service.py`)

- **`trigger_review(contract_id, current_user)`**:校验合同 + 权限 + 前置校验(analysis_status=completed)→ 读取字段 + 全文 → 建 ReviewReport(pending→running)→ 同步执行 ContractReviewAgent → 落库 risks/risk_level/summary/tool_calls_log → commit。
- **`get_review(review_id, current_user)`**:查询审核报告(含 risks / tool_calls_log),通过 contract_id 关联校验 employee 权限(他人合同 404 防枚举)。
- **`list_contract_reviews(contract_id, current_user, page, size)`**:合同审核历史分页。
- **`list_reviews(current_user, page, size, risk_level, status)`**:全局审核列表(含合同摘要),employee 仅可见自己合同的审核。
- 权限设计:admin / contract_manager 可审核任意合同;employee 触发审核由 API 层 `@role_required` 拦截(403);employee 查询他人合同审核返回 404。

#### API 层(4 个新接口,1 个新 Blueprint)

- **`POST /api/v1/contracts/{id}/review`**:触发合同 AI 风险审核(需 admin/contract_manager)。返回 `{review, contract}`。同步执行,Agent 失败时 ReviewReport 标记 failed 但接口仍 200(已落库)。
- **`GET /api/v1/contracts/{id}/reviews`**:合同审核历史(需 JWT,分页)。
- **`GET /api/v1/reviews`**:全局审核列表(需 JWT,分页 + risk_level + status 过滤)。
- **`GET /api/v1/reviews/{id}`**:审核报告详情(需 JWT,含 risks / tool_calls_log)。
- 新增 `review` Blueprint(前缀 `/api/v1/reviews`);合同相关 2 个接口挂在 `contract_api_bp`。

#### 前端(合同审核菜单 + 审核详情页 + 合同详情触发按钮)

- **`ReviewList.vue`**:审核报告列表(分页 / 风险等级过滤 / 状态过滤 + 合同摘要 + 风险标签)。
- **`ReviewDetail.vue`**:审核报告详情(总体风险等级卡片 + 风险列表 + 风险依据 + 修改建议 + 知识库引用来源 + Agent 工具调用轨迹)。
- **`ContractDetail.vue`**:新增 "AI 风险审核" 按钮(仅 admin/contract_manager + analysis_status=completed 可见;确认对话框 → 触发审核 → 跳转审核详情)。
- **`api/review.js`**:`triggerContractReview` / `getReviewDetail` / `listReviews` / `listContractReviews` 四个 API 函数(超时 300s)。
- **`SidebarMenu.vue`**:新增"合同审核"菜单项(/reviews)。
- **`router/index.js`**:新增 `reviews` / `reviews/:id` 两条路由。
- **`constants.js`**:新增 `REVIEW_STATUS` / `RISK_LEVEL` / `RISK_SEVERITY` 枚举与标签;版本号 → `v0.7.0`。

### 变更(Changed)

- **`__init__.py`(Application Factory)**:注册 `ReviewReport` 模型;注册 `review` Blueprint。
- **`api/contract/routes.py`**:新增 `POST /contracts/{id}/review` 与 `GET /contracts/{id}/reviews` 两个路由(挂在 contract_api_bp)。

### 兼容性(Backward Compatibility)

- **Sprint 0/1/2/3/4 架构未调整**:Application Factory / Blueprint / JWT / 角色控制 / 合同生命周期 / Document Pipeline / AnalysisTask / ContractField / Knowledge Layer 全部保留。
- **禁止修改 Sprint 3 Pipeline 与 Sprint 4 Knowledge Layer 核心逻辑**(任务书约束)。
- **Agent 仅通过只读接口复用**:`analysis_service.get_contract_fields` / `vector_store_registry.retriever.retrieve` / `_build_context_and_references`,不修改其源码。
- **Agent 同步执行**:Sprint 5 不引入 Celery / Redis / 异步任务队列(任务书约束)。
- **LLM 不可用不阻塞**:Agent 走 `risk_rule_tool` 兜底,ReviewReport 标记 success 但 summary 注明 LLM 不可用,接口仍 200。

### 约束遵循(Constraints Compliance)

- ✅ 不引入 Agent / LangGraph / Workflow / MCP 框架(手写 ReAct 循环)
- ✅ 不引入 Redis / Celery / Elasticsearch / Milvus / pgvector
- ✅ 不修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
- ✅ 不修改 Sprint 4 Knowledge Layer 核心逻辑(Embedding / VectorStore / Retriever)
- ✅ 仅使用 FAISS + sentence-transformers + DeepSeek
- ✅ Prompt 版本化管理(prompts/contract_review_v1.md)
- ✅ Tool 无状态 / 独立 / 可复用 / 可测试
- ✅ API 层不直接调用 Agent / LLM / Retriever(通过 review_service)
- ✅ 禁止 `print()` / `return str(e)`,统一 logger + 自定义异常

### 测试结果

- **Flask 启动自检**:✅ 通过(4 个 review 路由全部注册,FAISS 索引加载正常)
- **Agent 单元测试**:✅ 通过(3 个 Tool 注册 / Context 构造 / Prompt 加载 / AgentResult 状态)
- **RAG 引用结构测试**:✅ 通过(document_title / chunk_id / page_number / score 4 个必需字段全部存在且类型正确)
- **风险规则测试**:✅ 通过(11 条规则覆盖 4 类风险:付款 R001/R002、金额 R003/R004、期限 R005/R006/R007、关键条款缺失 R008-R011;3 个场景全部正确触发)
- **API 接口测试**:✅ 14/14 通过(权限拦截 403 / 不存在 404 / 非法参数 400 / 无 token 401 / 触发审核生成 5 条风险 / 详情结构完整 / employee 隔离 404)
- **前端构建**:✅ 通过(`npm run build` 成功,ReviewList / ReviewDetail / review API 全部编译通过)

### 遗留问题(Known Issues)

- **LLM 调用**:测试环境 DEEPSEEK_API_KEY 未配置或网络不通,Agent 走兜底路径(仅 risk_rule_tool)。生产环境配置可用 API_KEY 后,Agent 将完整执行 ReAct 循环(选 Tool → 综合分析 → final_report)。
- **Agent 同步执行**:当前审核接口同步阻塞(复杂合同可能 10-30s)。Sprint 8 计划引入 Celery 异步任务队列。
- **知识库为空**:RAG 检索无命中,knowledge_search_tool 返回空 references。需先通过 Sprint 4 知识库管理上传企业合同规范 / 法规 / 历史合同。

---

## [v0.6.0] - 2026-08-05

### Sprint 4 - 知识管理与 RAG 基础(Knowledge Layer + RAG Foundation)

建立企业级 Knowledge Layer 并完成 RAG 基础能力:知识文档上传 → Loader → Chunk(含 metadata + overlap)→ Embedding → FAISS → Retriever → DeepSeek → Answer。彻底解决 Sprint 3 Final Check 的三个 Chunk 问题(缺 Metadata / 未持久化 / 无 Overlap),为 Sprint 5(合同审核 Agent)提供知识检索能力。

### 新增(Added)

#### 数据模型层(2 张新表)

- **`knowledge_documents` 表**:知识文档元信息(doc_no / title / file_info / text_content / chunk_count / embedding_status / vector_indexed / uploader_id / status 软删)。独立于 Sprint 3 合同 `documents` 表,职责分离。
- **`knowledge_chunks` 表**:知识 Chunk 持久化(document_id / chunk_index / page_number / start_offset / end_offset / token_count / text / metadata / vector_id)。解决 Sprint 3 Final Check 三个问题:含完整 metadata + 持久化 + overlap 偏移记录。

#### Knowledge Layer(`backend/app/knowledge/`,五层解耦)

- **loader/**:`BaseLoader` 抽象 + `PdfLoader`(pdfplumber)/ `DocxLoader`(python-docx)/ `TxtLoader`,按扩展名注册,文件 → Page 列表。
- **parser/**:`parse_document` 编排 Loader + 构建 `page_map`(页区间映射),供 chunker 定位 chunk 页码;`locate_page` 按偏移定页。
- **chunk/**:`Chunk` 数据对象(含 page_number/offset/token_count/metadata)+ `BaseChunker` 抽象 + `SemanticChunker`(递归字符切分,chunk_size=500, overlap=200, min_chunk_size=100)。
- **embedding/**:`BaseEmbedding` 抽象 + `SentenceTransformerEmbedding`(BAAI/bge-small-zh-v1.5,512 维,归一化向量;懒加载 + 本地物化下载规避 Windows 符号链接问题)。
- **vectorstore/**:`BaseVectorStore` 抽象 + `FaissVectorStore`(IndexFlatIP + IndexIDMap2,支持 add/search/delete/save/load;vector_id 自增分配 + meta.json 持久化)。
- **retriever/**:`BaseRetriever` 抽象 + `DenseRetriever`(TopK=5 + score_threshold=0.35;预留 Hybrid Search 扩展)。
- **prompts/**:`rag_answer.md`(Prompt v1.0:仅依据检索内容回答 / 禁止编造 / 未命中明确说明 / 保留 `[文档n]` 引用标注)。
- **services/**:`knowledge_service`(上传/列表/详情/删除)+ `rag_service`(检索→context→DeepSeek→Answer)+ `vector_store_registry`(组件单例 + 启动加载 FAISS + DI 组装)。

#### API 层(5 个新接口,2 个新 Blueprint)

- **`POST /api/v1/knowledge/upload`**:上传知识文档(需 admin/contract_manager;同步 Embedding + FAISS)。
- **`GET /api/v1/knowledge`**:知识文档分页列表(需 JWT;含 chunk_count / embedding_status)。
- **`GET /api/v1/knowledge/{id}`**:知识文档详情(需 JWT;含 chunks 概要前 3 个预览)。
- **`DELETE /api/v1/knowledge/{id}`**:删除知识文档(需 admin/contract_manager;软删 + 从 FAISS 移除向量)。
- **`POST /api/v1/rag/query`**:RAG 问答(需 JWT;返回 answer + references + score + hit_count)。
- 新增 `knowledge` Blueprint(前缀 `/api/v1/knowledge`)+ `rag` Blueprint(前缀 `/api/v1/rag`)。

#### 前端(知识库管理菜单 + RAG Playground)

- **`KnowledgeList.vue`**:知识文档列表(分页/关键字/embedding_status 过滤 + Embedding 状态标签 + Chunk 数量)。
- **`KnowledgeUpload.vue`**:上传知识文档(pdf/docx/txt,角色控制 employee 不可见)。
- **`KnowledgeDetail.vue`**:知识文档详情(含 chunks 预览)。
- **`RagPlayground.vue`**:RAG 问答 Playground(用户问题 + 命中 Chunk + 相似度进度条 + LLM 回答 + 引用来源)。
- **`EmbeddingStatusTag.vue`**:Embedding 状态标签组件(pending/processing/completed/failed)。
- **`api/knowledge.js`**:`uploadKnowledgeDocument` / `getKnowledgeList` / `getKnowledgeDetail` / `deleteKnowledgeDocument` / `queryRag` 五个 API 函数。
- **路由 + 菜单**:新增 `knowledge` / `knowledge/upload` / `knowledge/playground` / `knowledge/:id` 四条路由;`SidebarMenu` 新增"知识库管理"菜单组(知识文档 / 上传知识 / RAG 问答)。
- **`constants.js`**:新增 `EMBEDDING_STATUS` 常量;版本号 → `v0.6.0`。
- **`router/index.js`**:新增 `meta.roles` 角色级路由守卫(上传页限 admin/contract_manager)。

#### 配置与依赖

- **`.env.example`**:新增 `EMBEDDING_MODEL` / `VECTOR_STORE_DIR` / `VECTOR_INDEX_NAME` / `RETRIEVER_TOP_K` / `RETRIEVER_SCORE_THRESHOLD` 五项配置。
- **`config/settings.py`**:新增 Embedding & Vector Store 配置加载。
- **`requirements.txt`**:新增 `sentence-transformers==2.7.0` / `faiss-cpu==1.8.0` / `python-docx==1.1.0` / `numpy>=1.24,<2.0`。

### 变更(Changed)

- **`__init__.py`(Application Factory)**:注册 KnowledgeDocument / KnowledgeChunk 模型;注册 `knowledge` / `rag` Blueprint;启动时调用 `vector_store_registry.load(app)` 加载已存 FAISS 索引。

### 兼容性(Backward Compatibility)

- **Sprint 0/1/2/3 架构未调整**:Application Factory / Blueprint / JWT / 角色控制 / 合同生命周期 / Document Pipeline / AnalysisTask / ContractField 全部保留。
- **禁止修改 Sprint 3 的 Document / AnalysisTask / ContractField 表**(任务书约束)。
- **知识 Chunk 与合同 Pipeline chunk 完全独立**:合同 chunk 为内存 transient 产物;知识 chunk 为持久化检索单元。

### 测试结果

- **端到端测试全部通过**:文档上传(2 份)/ Chunk 持久化(每份 1 chunk)/ Embedding 生成(bge-small-zh-v1.5 dim=512)/ FAISS 建索引(size=1→2)/ TopK 检索(hits=2 命中=2)/ RAG 问答(DeepSeek 200 OK)/ 空知识库(向量库为空跳过检索)/ 重复上传(第 2 份成功)/ 删除知识(FAISS 移除 1 条向量 + 软删)/ 权限控制(employee 403 / JWT 401)/ 参数校验(空 query 400 / 不支持类型 400)/ 前端联调(CORS preflight + 请求 200)/ Sprint 0~3 回归(health / auth / contracts / analysis 均 200)。
- **Sprint 0/1/2/3 回归正常**:无破坏性变更。

### 已知限制

- **同步执行**:Sprint 4 禁止 Celery / Redis,Embedding + FAISS + RAG 均同步执行;首次上传触发模型下载(≈95MB)耗时较长,后续上传仅需 encode。
- **LLM 依赖**:RAG 问答依赖 `DEEPSEEK_API_KEY`;未配置时仍返回 references,answer 标注失败原因。
- **无 Hybrid Search**:本阶段仅 Dense 检索(向量);`DenseRetriever` 预留 Hybrid 扩展点,未来可新增 `HybridRetriever`(向量 + 关键词)不改 service。
- **无重试接口**:Embedding 失败后无独立重试接口,需删除后重新上传(Sprint 8 异步化后可补)。
- **模型物化路径**:bge-small-zh-v1.5 物化到 `storage/models/bge-small-zh-v1.5/`(规避 Windows 符号链接权限问题),首次下载后离线可用。

---

## [v0.5.0] - 2026-08-05

### Sprint 3 - Document Pipeline(AI 合同解析流水线升级)

将 Sprint 0/2 的同步 AI 解析 Demo 升级为企业级 Document Pipeline(Stage 设计),引入任务化追踪、结构化字段存储、Prompt 版本化管理,为 Sprint 4(RAG)/ Sprint 5(Agent)奠定数据与流程基础。

### 新增(Added)

#### 数据模型层(3 张新表)

- **`documents` 表**:文档元信息(文件 + 提取文本),从 `contracts` 解耦;`text_content` 落库支持失败重跑免重新 OCR。
- **`analysis_tasks` 表**:分析任务(`task_no` / `status` / `current_stage` / `stages_log`),任务化追踪每次分析执行。
- **`contract_fields` 表**:结构化字段(字段级 `confidence` + `source_text`),替代 Sprint 2 的 `analysis_result` JSON 列;支持 8 字段(`contract_no` / `contract_name` / `party_a` / `party_b` / `amount` / `sign_date` / `payment_method` / `valid_period`)。

#### AI Pipeline 层(`backend/app/ai/pipeline/`)

- **Stage 架构**:6 个职责单一的 Stage,通过 `PipelineContext` 传递数据,Stage 间不直接互相调用。
  - `extract_stage`:PDF 文本提取(pdfplumber,复用现有函数)
  - `ocr_stage`:OCR 兜底(DeepSeek Vision,仅 extract 失败时触发;Sprint 3 不支持 PDF 转图片)
  - `clean_stage`:文本清洗(复用 `text_utils.clean_text`)
  - `chunk_stage`:文本切分(按段落 + 长度上限,避免超 token)
  - `llm_stage`:LLM 结构化字段提取(8 字段 JSON,缺失返回 null,禁止编造)
  - `save_stage`:字段落库(`ContractField`)
- **`base.py`**:`BaseStage` 抽象基类 + `StageResult`(success / skipped / failed)。
- **`context.py`**:`PipelineContext` 数据载体。
- **`runner.py`**:Pipeline 编排器,状态机驱动 Stage 执行,实时更新 `task.current_stage` 与 `stages_log`。
- **`prompts/contract_extract_v1.md`**:字段提取 Prompt 从代码剥离,版本化管理(v1.0)。

#### 业务服务层

- **`backend/app/services/analysis_service.py`**:分析任务编排(触发分析 / 查询任务 / 获取字段);含 Sprint 2 旧合同降级逻辑(`analysis_result` → `legacy_json`)。

#### API 层(3 个新接口)

- **`POST /api/v1/contracts/{id}/analysis`**:触发合同分析(创建 Task + 同步执行 Pipeline)。
- **`GET /api/v1/analysis/{task_id}`**:查询任务状态(含 `stages_log` 进度)。
- **`GET /api/v1/contracts/{id}/fields`**:获取合同字段(优先 `contract_fields`,降级 `analysis_result`)。
- 新增 `analysis` Blueprint(前缀 `/api/v1/analysis`)。

#### 前端

- **`ContractDetail.vue` 升级**:AI 分析任务进度展示(6 个 Stage 状态)+ 结构化字段表格(8 字段 + confidence 进度条 + 来源文本)+ "开始分析 / 重新分析"按钮 + 数据来源标识。
- **`constants.js`**:新增 `TASK_STATUS` / `PIPELINE_STAGES` / `STAGE_LABELS` / `STAGE_STATUS` 等常量;`ANALYSIS_STATUS` 新增 `pending`;版本号 → `v0.5.0`。
- **`contract.js`**:新增 `triggerContractAnalysis` / `getAnalysisTask` / `getContractFields` 三个 API 函数;上传超时从 180s 缩短到 60s(不再含 AI)。
- **`ContractUpload.vue`**:提示文案更新("上传后待分析,请在详情页点击开始分析")。

### 变更(Changed)

- **`contract_service.create_contract`**:不再自动调用 `analyze_document`;`analysis_status` 从 `processing` 改为 `pending`(等待手动触发);上传接口立即返回,不再阻塞等待 AI。
- **`AnalysisTask` 状态回写 `Contract.analysis_status`**:`success → completed` / `failed → failed` / `running → processing`,保持前端兼容。
- **`__init__.py`(Application Factory)**:注册 Document / AnalysisTask / ContractField 模型;注册 `analysis` Blueprint。

### 兼容性(Backward Compatibility)

- **Sprint 2 旧合同**:`contracts.analysis_result` JSON 列保留(只读);详情 / 字段接口降级读取,并补齐为 8 字段(`signing_date → sign_date` 映射,新字段为 null)。
- **Sprint 0/1 架构未调整**:Application Factory / Blueprint / JWT / 角色控制 / 健康检查全部保留。
- **`document_service.analyze_document` / `process_upload` 保留**:legacy HTML 上传页(`/`)仍可用;新 Pipeline 不依赖它们但复用其底层函数(`extract_text_from_pdf` / `extract_text_using_deepseek_ocr`)。

### 测试结果

- **39/39 PASS**:涵盖健康检查 / JWT 登录 / 上传(pending)/ 触发分析(LLM 失败)/ Pipeline 6 Stage 状态(extract✓ ocr⤵ clean✓ chunk✓ llm✗ save⤓)/ 任务查询 / 字段获取(空)/ 异常(404/401/403)/ OcrStage 单元测试(扫描 PDF / 文本 PDF / 图片)/ 旧合同降级(legacy_json,8 字段)/ 状态机回归 / Sprint 0 AI 能力回归。
- **Sprint 0/1/2 回归正常**:无破坏性变更。

### 已知限制

- **同步执行**:Pipeline 仍同步执行(Sprint 3 禁止 Celery / Redis);大文件可能耗时较长,接口超时设 300s。
- **LLM 失败**:当前 `DEEPSEEK_API_KEY` 为占位符,LLM Stage 必失败;配置真实 Key 后即可成功提取字段。
- **扫描 PDF**:OCR 仅支持图片,Sprint 3 不支持 PDF → 图片转换;扫描 PDF 会标记 `failed`("OCR 仅支持图片文件")。
- **AI 层 legacy `print()`**:`deepseek_service.py` / `ocr_service.py` 内部仍保留 legacy `print()`(复用约束);新 Pipeline 的 Stage 已全部使用 `logger`。

---

## [v0.4.1] - 2026-08-05

### Sprint 2 Release Candidate(RC)验收

本版本为 Sprint 2 的 RC 打磨版本,**不新增业务功能**,仅修复代码审查问题、优化体验、补全文档,使系统达到可交付状态。

### Fixed

- **"我的账户"页面缺失(Critical)**:新建 `frontend/src/pages/Profile.vue`,展示用户名 / 角色 / 注册时间 / Token 前缀 / 退出登录入口;新增 `/profile` 路由;修复 Header 下拉菜单与 Dashboard 快捷卡片的跳转。
- **`document_service.py` 残留 `print()`(Medium)**:将 `extract_text_from_pdf` / `process_upload` / `analyze_document` 中所有 `print()` 替换为 `logger.info()` / `logger.debug()` / `logger.warning()`,统一日志输出渠道。
- **异常详情泄露给客户端(Medium - 安全)**:`contract_service.py` 与 `document_service.py` 中 `f'...{e}'` / `str(e)` 拼入 BusinessError message 的位置全部脱敏,改为通用提示;详细异常通过 `logger.exception()` 记录。
- **N+1 查询(Low - 性能)**:`contract_service.get_contract_list()` 增加 `joinedload(Contract.creator)` 预加载,消除列表场景下 `to_dict()` 触发 creator 懒加载的 N+1 问题。
- **输入长度校验缺失(Low)**:`contract_service.create_contract()` 增加 `contract_type`(≤64)/ `title`(≤255)/ `description`(≤5000)长度校验;`auth_service.register()` 增加 `username`(≤64)/ `password`(≤128)长度校验,超长抛 `ValidationError(400)`。
- **搜索空状态不区分(Low - UX)**:`ContractList.vue` 的 `empty-text` 改为 computed,有筛选条件时提示"未找到匹配的合同,请调整搜索条件",无筛选时提示"暂无合同数据"。

### Changed

- `frontend/src/pages/contract/ContractList.vue`:`empty-text` 由静态字符串改为 `emptyText` computed 属性。
- `frontend/src/router/index.js`:AdminLayout children 新增 `/profile` 路由。
- `frontend/src/layouts/AdminLayout.vue`:`handleCommand('profile')` 改为 `router.push('/profile')`。
- `frontend/src/pages/Dashboard.vue`:"我的账户"快捷卡片增加 `@click` 跳转。
- `backend/app/services/document_service.py`:所有 `print()` → `logger`;异常 message 脱敏;临时文件清理增加异常保护。
- `backend/app/services/contract_service.py`:增加输入长度校验;异常 message 脱敏;`get_contract_list` 增加 `joinedload`。
- `backend/app/services/auth_service.py`:增加 `username` / `password` 长度校验。

### 新增

- `frontend/src/pages/Profile.vue`:我的账户页(用户信息 + Token 信息 + 退出登录)。
- `docs/SPRINT2_CODE_REVIEW.md`:RC 阶段全面代码审查报告。
- `docs/SPRINT2_RC_REPORT.md`:RC 阶段交付报告。

### 测试结果

- **后端 API 自检 10/10 PASS**:Health / Login / Profile(含 created_time) / ContractList(joinedload) / ContractDetail / 状态流转 draft→reviewed / 非法跳转拦截 400 / employee 隔离 404 / 无 Token 401 / 输入校验(超长 title 400)。
- **代码审查**:6 项问题全部修复(F1 Critical + B1/B2 Medium + B3/B4/F6 Low),无架构性问题。

### 保留(自检确认未受影响)

- Sprint 0 工程化架构未调整;Sprint 1 用户认证未调整;Sprint 2 合同管理业务逻辑未改变。
- OCR / DeepSeek AI 分析能力完整保留(`analysis_status=completed` 验证通过)。
- AI 层(`ai/llm/deepseek_service.py`、`ai/ocr/ocr_service.py`)的 legacy `print()` 暂不修改(复用约束),列为已知限制,留待 Sprint 3 统一处理。

### 已知限制

- AI 层 legacy `print()`(deepseek_service 36 处 / ocr_service 28 处)暂未替换为 logger(遵循"不重新开发 AI 能力"约束);Sprint 3 重构 Document Pipeline 时统一处理。
- `analysis_result` JSON 列内联存储、AI 同步调用、`db.create_all()` 建表等架构限制保留(与 v0.4.0 一致)。

---

## [v0.4.0] - 2026-08-05

### 新增(Sprint 2 Phase A - Admin Console 基础框架)

- **前端项目骨架**:`frontend/`(Vue3 + Vite + Element Plus + Pinia + Vue Router + Axios,JavaScript,不用 TypeScript)。
  - `package.json` / `vite.config.js`(端口 5173,alias `@` → `src`)。
  - `.env.development`(`VITE_API_BASE_URL=http://127.0.0.1:5001/api/v1`)、`.env.production`(`/api/v1` 同源部署)。
- **CORS 后端补全**:`backend/app/extensions/cors.py` 新建 `init_cors(app)`,仅对 `/api/*` 开放,Origin 从 `CORS_ORIGINS` 配置读取(不用 `*`)。
  - `requirements.txt` 新增 `flask-cors==4.0.0`。
  - `app/__init__.py` 在 `init_jwt` 后追加 `init_cors(app)`(3 行)。
  - `config/settings.py` 新增 `CORS_ORIGINS` 配置项(从 `.env` 读取)。
  - `backend/.env.example` 追加 `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`。
- **Axios 统一封装**:`frontend/src/api/request.js`,BaseURL 从环境变量读取,请求拦截器注入 `Authorization: Bearer {token}`,响应拦截器统一处理 `{code,message,data}`,401 自动清除登录态并跳转登录。
- **Pinia 认证 Store**:`frontend/src/store/auth.js`,仅管理 `token` / `user`(localStorage 持久化),getters:`isLoggedIn` / `isAdmin` / `isManager`,actions:`login` / `fetchProfile` / `logout`。
- **路由与守卫**:`frontend/src/router/index.js`,路由表 + 全局前置守卫(JWT 校验 + 刷新页面恢复 profile + 登录页已登录自动跳 dashboard)。
- **登录页**:`frontend/src/pages/Login.vue`,Element Plus 表单 + 校验 + 回车提交,调用真实 `/auth/login` 接口。
- **后台布局**:`frontend/src/layouts/AdminLayout.vue`(Header + Sidebar + Main),Header 含系统名称/版本/用户下拉(我的账户/退出登录),SidebarMenu 根据路由高亮。
- **侧边栏菜单**:`frontend/src/components/SidebarMenu.vue`,当前菜单:仪表盘 / 合同管理 / 上传合同(Progressive Admin Design,不创建未来菜单)。
- **Dashboard**:`frontend/src/pages/Dashboard.vue`,欢迎信息 + 当前用户/角色 + 系统版本 + 快捷入口卡片 + 系统信息描述列表(不实现统计图表)。
- **常量与工具**:`frontend/src/utils/constants.js`(角色枚举/合同状态枚举/状态机转换矩阵/标签映射/版本号)、`format.js`(`formatFileSize`/`formatTime`/`truncate`)。
- **404 页**:`frontend/src/pages/NotFound.vue`。
- **全局样式**:`frontend/src/styles/index.css`,样式重置 + 公共类(page-container / flex / mb-16 等)。
- **应用入口**:`frontend/src/main.js`,注册 Vue + Element Plus(中文 locale)+ Pinia + Router + 全局图标。
- **根 .gitignore** 追加 `frontend/node_modules/`、`frontend/dist/`。

### 新增(Sprint 2 Phase B - 合同管理业务页面)

- **合同 API 模块**:`frontend/src/api/contract.js`,封装 4 个接口(`uploadContract` / `listContracts` / `getContractDetail` / `updateContractStatus`)。
- **StatusTag 组件**:`frontend/src/components/contract/StatusTag.vue`,根据 status 渲染 el-tag(draft=info / reviewed=success / archived=warning),可选显示 AI 分析状态标签(processing/completed/failed)。
- **合同列表页**:`frontend/src/pages/contract/ContractList.vue`:
  - 筛选栏(关键字 + 状态下拉 + 搜索/重置)。
  - el-table 列:合同编号 / 标题 / 类型 / 状态(StatusTag) / 创建人 / 创建时间 / 操作(查看详情)。
  - el-pagination 分页(10/20/50/100 每页),联动后端 `page`/`size`。
  - 调用 `listContracts(params)` 真实接口,无假数据。
- **上传合同页**:`frontend/src/pages/contract/ContractUpload.vue`:
  - el-upload 拖拽上传(accept=.pdf,.png,.jpg,.jpeg,limit=1)。
  - 表单:合同类型 / 合同标题 / 描述(均可选)。
  - 前端校验:类型(与后端 ALLOWED_EXTENSIONS 一致)+ 大小(<=10MB)。
  - 调用 `uploadContract(formData)` 真实接口,上传中 Loading + 按钮禁用。
  - 成功 → ElMessage.success + 跳转合同详情页(查看 AI 分析结果)。
  - 上传会真实触发 DeepSeek AI 分析(复用 Sprint 0 能力,180s 超时)。
- **合同详情页**:`frontend/src/pages/contract/ContractDetail.vue`:
  - 顶部操作栏:返回 + 当前状态标签。
  - 基本信息卡片:合同编号 / 标题 / 类型 / 状态 / 描述。
  - 文件信息卡片:文件名 / 大小。
  - 创建人卡片:用户名 / 角色 / 创建时间 / 更新时间。
  - AI 分析结果卡片:分析中(Loading)/ 失败(warning)/ 完成(el-descriptions 展示 contract_name / party_a / party_b / amount / signing_date)。
  - 状态流转卡片(**仅 admin / contract_manager 可见**,基于 `canUpdateStatus` computed):
    - 显示当前状态 + 可流转目标按钮(基于 `STATUS_TRANSITIONS`)。
    - 终态(archived)显示"终态,不可流转"。
    - 点击流转 → ElMessageBox 确认 → 调 `updateContractStatus` → 刷新。
    - employee 隐藏整张卡片。
- **路由接入**:Phase A 占位的 3 个合同路由替换为真实组件;SidebarMenu 启用合同管理与上传合同入口。
- **文档**:`docs/FRONTEND_IMPLEMENTATION_PLAN.md`(实施计划)、`docs/FRONTEND_ARCHITECTURE.md`(前端架构设计)。

### 新增(Sprint 2 - 合同生命周期管理后端)

- **合同模型**:`app/models/contract.py`,定义 `contracts` 表(id / contract_no / title / contract_type / description / creator_id / status / file_name / file_path / file_size / analysis_status / analysis_result / created_time / updated_time)。
  - `creator_id` 外键关联 `users.id`(User → Contract 一对多,通过 `backref`,不修改 user.py)。
  - `contract_no` 唯一索引,自动生成 `CT-YYYYMMDDHHMMSS-XXXXXXXX`。
  - 生命周期状态机:仅实现 `draft` / `reviewed` / `archived`(`uploaded` / `analyzing` / `approved` 预留);`STATUS_TRANSITIONS` 定义单向流转,`is_valid_transition()` 校验。
  - AI 分析状态:`pending` / `processing` / `completed` / `failed`(独立维度,无状态机)。
  - `analysis_result` 为 `db.JSON` 列存储 AI 提取字段(详情接口读取已有结果);Sprint 3 将迁移至独立 `contract_fields` 表。
  - `to_dict()` 不暴露 `file_path`(内部路径),仅返回 `file_info:{name,size}`。
- **合同业务服务**:`app/services/contract_service.py`(模块级函数,对标 auth_service 风格):
  - `create_contract`:文件保存(UUID 命名到 `uploads/contracts/`)→ 建记录 → 调用已有 AI 分析 → 回写结果;AI 失败 ≠ 上传失败(记录仍持久化)。
  - `get_contract_list`:分页 / 关键字(title+contract_no 模糊)/ 状态过滤 / 创建人过滤 / `created_time DESC` 排序。
  - `get_contract_detail`:含创建人 / 状态 / 文件信息 / AI 分析结果。
  - `update_contract_status`:状态机校验,非法跳转抛 `BusinessError`。
- **合同 RESTful API**:`app/api/contract/routes.py` 新增 `contract_api_bp`(Blueprint,前缀 `/api/v1/contracts`,独立于现有 `contract_bp` HTML 路由):
  - `POST   /api/v1/contracts/upload` 上传合同(需 JWT)
  - `GET    /api/v1/contracts` 合同分页列表(需 JWT)
  - `GET    /api/v1/contracts/{id}` 合同详情(需 JWT)
  - `PATCH  /api/v1/contracts/{id}/status` 更新合同状态(需 admin / contract_manager)
- **AI 复用函数**:`app/services/document_service.py` 新增 `analyze_document(file_path, file_type)`,复用既有 `extract_text_from_pdf` / `extract_text_using_deepseek_ocr` / `extract_contract_fields`,不修改它们;`process_upload` 不动。
- **权限落地**:Service 层数据级过滤(employee 仅看 `creator_id == 自己`);employee 访问他人合同详情返回 **404**(防 ID 枚举);状态更新仅 admin / contract_manager(`@role_required` 拦截)。
- **文件管理**:统一 `uploads/contracts/{uuid}.ext`,UUID 命名避免重名;DB 存 `file_path`。
- **文档**:`docs/DATABASE_DESIGN.md`(contracts 表)、`docs/API_DESIGN.md`(合同模块 RESTful API + PATCH 说明)。

### Changed

- `create_app()`:app context 内新增 `Contract` 模型导入(确保 `db.create_all()` 建 contracts 表);注册 `contract_api_bp`(`/api/v1/contracts`);在 `init_jwt(app)` 后追加 `init_cors(app)`。
- `app/api/contract/routes.py`:**追加** `contract_api_bp` 定义 + 4 个路由 + `_get_current_user` 辅助;`contract_bp` 与 `index()` HTML 路由一字不动。
- `app/services/document_service.py`:**追加** `analyze_document` 函数;`process_upload` / `extract_text_from_pdf` 不动。
- `backend/requirements.txt`:追加 `flask-cors==4.0.0`(Sprint 2 Phase A)。
- `backend/app/config/settings.py`:追加 `CORS_ORIGINS` 配置项(从 `.env` 读取)。
- `backend/.env.example`:标题更新至 v0.4.0;追加 `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`。
- `README.md`:更新至 v0.4.0,新增合同生命周期管理能力说明 + Admin Console 前端启动方式 + 测试账号 + 前端架构文档引用。
- `docs/SPRINT2_REPORT.md`:追加前端章节(Phase A / Phase B 实施记录 + 自检结果)。

### 保留(自检确认未受影响)

- Sprint 0 工程化架构未调整;`/` HTML 上传页行为不变;OCR / DeepSeek 调用逻辑与 Prompt 不变。
- Sprint 1 用户认证未调整;`users` 表、JWT、`role_required`、auth 接口全部保留。
- `models/user.py` 未修改(Contract 通过 `backref` 关联);`ai/*`、`auth_service.py`、`config/settings.py`、`decorators/*`、`utils/*`、`legacy/*`、`requirements.txt` 均未修改。
- 测试 5 真实 DeepSeek API 调用成功,`analysis_status=completed`,AI 字段提取正常。

### 测试结果

- **后端自检 16/16 PASS**:Flask 启动 / contracts 表建立 / Sprint 0 回归(HTML + health)/ Sprint 1 回归(注册+登录)/ 合同上传(DeepSeek 真实调用) / 无 JWT 401 / 缺文件 400 / 不允许类型 400 / 列表 admin 全部 / 列表 employee 隔离 / 详情含 analysis_result / 详情 employee 防枚举 404 / 状态 draft→reviewed / reviewed→archived / 非法跳转 400 / employee 无权限 403。
- **前端 Phase A 自检 11/11 PASS**:登录页显示 / 三角色登录 / Dashboard 跳转 / 用户信息显示 / 刷新 token 持久化 / 退出登录 / 无 token 自动跳登录 / CORS 正常 / 错误密码提示 / Sprint 0 legacy `/` 仍可访问 / Sprint 1 profile 接口正常。
- **前端 Phase B 自检 11/11 PASS**:合同列表加载真实数据 / 分页切换 / 关键字搜索 / 状态过滤 / 上传 PDF 真实调用 DeepSeek AI 并显示分析结果 / 详情页完整信息展示 / admin 状态流转 draft→reviewed→archived / contract_manager 可修改状态 / employee 隐藏状态按钮 / employee 仅看自己合同 / Token 过期自动跳登录。
- **浏览器端到端验证**:用 admin 账号登录 → 上传 test.pdf(API 触发 DeepSeek,analysis_status=completed,提取出 contract_name/party_a/party_b)→ 合同列表显示 → 详情页展示 AI 结果 → 状态流转 draft→reviewed→archived 全部成功;employee 账号验证合同列表为空(权限隔离)+ 访问他人合同 404(防枚举)。
- 详见 `docs/SPRINT2_REPORT.md`。

### 约束遵守

- 本阶段为合同管理 + Admin Console,**未**重新开发 OCR / DeepSeek / Document Parser,仅复用。
- 仅实现 `draft` / `reviewed` / `archived` 三状态,`uploaded` / `analyzing` / `approved` 预留。
- 未增加审批表 / 流程表 / 版本表(留待后续 Sprint)。
- 未新增 Repository 层(继续 API → Service → Model)。
- API 层不直接访问数据库、不直接调用 OCR/LLM,业务逻辑全部下沉至 `contract_service`。
- 禁止 `print()` / `return str(e)`;统一 Response / Exception / Logger。
- **前端约束**:使用 JavaScript(不用 TypeScript);CORS 仅开放 `/api/*`,Origin 白名单预留 `.env`(不用 `*`);Progressive Admin Design(只开发当前业务页面,不创建未来菜单 / 空白页 / 占位页);不引入任何后台模板。
- **分两阶段实施**:Phase A(基础框架:frontend 初始化 / Layout / Router / Pinia / Axios / 登录 / Dashboard / 权限菜单 / 前后端联调)→ Phase B(合同管理:合同列表 / 上传 / 详情 / 状态流转 / AI 分析结果展示)。

### 已知限制

- `analysis_result` 以 JSON 列内联存储于 `contracts` 表;Sprint 3 将迁移至独立 `contract_fields` 表(支持字段级 `confidence` 与多版本)。
- AI 分析为同步调用(与 `/` HTML 路由一致),大文件可能阻塞;Sprint 3+ 引入异步队列。
- 数据库建表仍用 `db.create_all()`;生产建议引入 Flask-Migrate(遗留项,自 Sprint 1 起)。

---

## [v0.3.0] - 2026-08-04

### 新增(Sprint 1 - 用户认证系统)

- **用户模型**:`app/models/user.py`,定义 `users` 表(id / username / password_hash / role / created_time / updated_time)。
  - username 唯一索引;role 枚举限定 `admin` / `contract_manager` / `employee`。
  - 密码使用 Werkzeug `generate_password_hash` 存储,**禁止明文**;`to_dict()` 不返回 `password_hash`。
- **JWT 扩展**:`app/extensions/jwt.py`,Flask-JWT-Extended 实例 + 异常统一回调(未提供 / 无效 / 过期 / 撤销 / 需刷新),全部返回 `{code, message, data}` 并记录日志。
- **认证服务**:`app/services/auth_service.py`,实现 `register` / `login` / `get_user_by_id`,JWT claims 携带 `role` + `username`。
- **认证接口**:`app/api/auth/routes.py`(Blueprint,前缀 `/api/v1/auth`):
  - `POST /api/v1/auth/register` 用户注册
  - `POST /api/v1/auth/login` 用户登录(返回 access_token + 用户信息)
  - `GET  /api/v1/auth/profile` 当前用户信息(需 JWT)
- **角色控制装饰器**:`app/decorators/role_required.py`,支持 `@role_required("admin")` / `@role_required("admin","contract_manager")`,内置 `@jwt_required()`,角色不符抛 `AuthError(403)`。
- **数据库建表**:`create_app()` 内 `app.app_context()` + `db.create_all()`(Sprint 1 起启用,Sprint 0 仅为 init_app)。
- **JWT 配置**:`JWT_SECRET_KEY` / `JWT_ACCESS_TOKEN_EXPIRES` / `JWT_TOKEN_LOCATION` 等从 `.env` 读取。
- **文档**:`docs/API_DESIGN.md`(实际实现 API 文档)、`docs/DATABASE_DESIGN.md`(users 表结构 / 索引 / 约束 / DDL)。

### Changed

- `create_app()`:在 `db.init_app` 后新增 `init_jwt(app)`;app context 内 `db.create_all()` 建 users 表;注册 `auth_bp`(`/api/v1/auth`)。
- `app/config/settings.py`:新增 JWT 配置段(`JWT_SECRET_KEY` 等从 `.env` 读取,默认值仅开发用)。
- `requirements.txt`:新增 `Flask-JWT-Extended==4.6.0`。
- `backend/.env.example`:补充 `JWT_SECRET_KEY`、`JWT_ACCESS_TOKEN_EXPIRES` 配置项。
- `README.md`:更新至 v0.3.0,补充用户认证能力说明、目录结构、环境变量表。

### 保留(自检确认未受影响)

- Sprint 0 工程化架构未调整(Application Factory / Blueprint / 分层 / 统一 Response / 统一 Exception / Logger / health 全部保留)。
- 合同上传页 `/` 行为不变(HTML 渲染)。
- OCR / DeepSeek 调用逻辑、Prompt、参数不变;测试 12 真实 DeepSeek 调用成功,字段提取正常。
- `legacy/` 旧版 Demo 原样保留。

### 测试结果

- 自检 12/12 PASS:Flask 启动 / Health / 注册成功 / 重复用户名 / 密码错误 / 登录成功 / JWT 验证 / JWT 无效 / JWT 过期 / Profile / role_required / 原合同分析(PDF + DeepSeek 真实调用)。
- 详见 `docs/SPRINT1_REPORT.md`。

### 约束遵守

- 本阶段仅做 Authentication(认证),**未实现**完整 RBAC / 部门 / 权限表 / 菜单 / 多租户。
- 未开发合同管理 / RAG / Agent 等新业务功能(留待 Sprint 2+)。
- API 层不直接访问数据库、不直接生成 JWT,业务逻辑全部下沉至 `auth_service`。

---

## [v0.2.1] - 2026-08-04

### 新增(Sprint 0 Release Check 基础设施)

- **统一 API 响应**:`app/utils/response.py` 提供 `success()` / `error()`,遵循 API_DESIGN 统一格式 `{code, message, data}`。
- **统一异常处理**:`app/utils/exceptions.py` 定义 `AppException` 及子类(Validation/Business/NotFound/Auth),全局 ErrorHandler 统一返回 JSON,禁止 `return str(e)`。
- **日志系统**:`app/extensions/logger.py`,Python logging + RotatingFileHandler,输出至 `logs/app.log`,覆盖启动/上传失败/OCR 异常/DeepSeek 异常/未捕获异常。
- **数据库初始化**:`app/extensions/db.py` 引入 `SQLAlchemy` 实例,`create_app()` 中 `db.init_app(app)`(仅初始化,不建表、不建模型)。
- **健康检查接口**:`GET /api/v1/health` 返回 `{code:200, message:"success", data:{status:"ok"}}`,不依赖 db/DeepSeek。
- **系统 Blueprint**:`app/api/system/routes.py`,前缀 `/api/v1`。

### Changed

- `create_app()` 集成 db.init_app / setup_logging / register_error_handlers / system_bp。
- AI 层与 Service 层 `traceback.print_exc()` 统一为 `logger.exception()`(异常处理方式统一,业务逻辑不变)。
- `requirements.txt`:移除未使用的 `langchain==0.1.10`;显式化 `langchain-core==0.1.53`;新增 `Flask-SQLAlchemy==3.1.1`。
- `.gitignore`:补充 `logs/`、`backend/logs/`、`*.db`、`*.sqlite`、`*.sqlite3`。
- 配置新增:`SQLALCHEMY_DATABASE_URI`、`SQLALCHEMY_TRACK_MODIFICATIONS`、`LOG_DIR`、`LOG_LEVEL`。

### 保留

- 合同上传页 `/` 行为不变(HTML 模板渲染,不纳入统一 JSON)。
- OCR / DeepSeek 调用逻辑、Prompt、参数不变(仅异常输出方式改为 logger)。
- `legacy/` 旧版 Demo 原样保留。

### 说明

- 详细检查结果见 `docs/SPRINT0_RELEASE_REPORT.md`、`docs/DEPENDENCY_REPORT.md`。
- 自检 10/10 PASS,DeepSeek 字段提取真实调用验证未受影响。

---

## [v0.2.0] - 2026-08-04

### 新增

- 引入工程化分层架构:Flask Application Factory(`create_app()`)+ Blueprint 模块化路由。
- 建立 Service / AI(ocr/llm)/ Utils / Config / Models(占位)/ Extensions(占位) 分层目录。
- 新增配置规范化:Flask 与 DeepSeek 配置集中至 `backend/app/config/settings.py`,敏感信息从 `.env` 读取。
- 新增独立入口 `backend/run.py`,与 legacy 解耦。

### Changed

- 将 legacy 单文件 `app.py` 的业务逻辑渐进式迁移至分层模块:
  - PDF 提取 → `backend/app/services/document_service.py`
  - DeepSeek Vision OCR → `backend/app/ai/ocr/ocr_service.py`
  - 合同字段提取 → `backend/app/ai/llm/deepseek_service.py`
  - 文件/文本工具 → `backend/app/utils/`
  - 路由 → `backend/app/api/contract/routes.py`
- API 层不再直接调用 OCR/LLM,统一经 Service 编排(职责分离)。
- `DEEPSEEK_API_BASE`、`DEEPSEEK_MODEL`、`SECRET_KEY` 由硬编码迁入 config + `.env`(默认值与 legacy 一致,行为不变)。

### 保留

- OCR 核心逻辑、DeepSeek 调用逻辑、Prompt、参数字节级原样保留(逐函数 diff 校验)。
- PDF 上传与分析能力完整保留(PDF 提取 parity 字节一致)。
- 前端模板 `templates/index.html` 字节级复制至 backend(UI 不变)。
- `legacy/` 旧版 Demo 原样保留,可独立运行。

### 说明

- 本版本为工程化重构,**未新增业务功能、未引入数据库/认证**(留待 Sprint 1)。
- 详细迁移过程见 `docs/SPRINT0_MIGRATION_PLAN.md` 与 `docs/SPRINT0_REPORT.md`。

---

## [v0.1.0] - 2026-08-04

### 新增

- 初始化合同AI分析 Demo。
- 实现 PDF 文件上传与 pdfplumber 文本提取。
- 实现基于 DeepSeek Vision API 的图片 OCR 识别。
- 实现基于 DeepSeek Chat API + LangChain 的合同关键字段提取（合同名称、甲方、乙方、金额、签署日期）。
- 实现合同上传与结果展示前端页面（Flask + Jinja2 + Bootstrap 5）。

### 说明

- 本版本为能力验证 Demo，采用单文件 Flask 架构。
- 作为后续企业级智能合同与投标管理平台重构的基础版本。

---

## 开发记录规范

每次代码修改记录分类：

- **新增**：新增功能
- **Changed**：修改功能
- **Fixed**：修复问题
- **Removed**：删除功能
- **Breaking Changes**：影响已有接口或架构的修改
