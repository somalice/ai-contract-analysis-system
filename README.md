# 智能合同与投标管理平台

> **当前版本: v1.0.0(Sprint 8 - Enterprise AI 增强)**
>
> 基于 Flask + LangChain + DeepSeek 的企业级智能合同与投标管理平台。
> v0.2.0 完成工程化分层重构;v0.2.1 完成 Release Check 补齐基础设施;
> v0.3.0 新增用户认证系统(JWT + 角色控制);
> v0.4.0 新增合同生命周期管理(上传/列表/详情/状态机 + 权限控制 + AI 复用)+ 企业级后台 Admin Console(Vue3 + Element Plus);
> v0.4.1 Sprint 2 RC:代码审查修复 + "我的账户"页面 + 输入校验 + N+1 优化 + 异常脱敏 + 日志统一 + UX 优化;
> v0.5.0 Sprint 3:将同步 AI 解析 Demo 升级为企业级 Document Pipeline(Stage 架构)+ 任务化追踪 + 结构化字段存储 + Prompt 版本化管理;
> v0.6.0 Sprint 4:建立企业级 Knowledge Layer(五层解耦)+ RAG 基础能力(FAISS + sentence-transformers + DeepSeek),彻底解决 Sprint 3 Final Check 的 Chunk 三大问题(metadata / 持久化 / overlap);
> v0.7.0 Sprint 5:引入手写 ReAct Contract Review Agent(LLM 决策 + 3 个无状态 Tool 执行:字段查询 / RAG 检索 / 规则检查),LLM 不可用时走 risk_rule_tool 兜底,生成结构化风险报告并持久化;
> v0.7.1 Sprint 5 Final:Agent 企业级可观测增强 — 修复 LLM 无法调用的关键 bug,Agent 现在真正走完整 ReAct 流程;新增 Agent Trace(每步 12 字段)+ Tool Observability + LLM 容错 + 前端 Timeline 展示;
> v0.8.0 Sprint 6:AI 合同自动生成系统(Contract Generation Pipeline)— 构建完整的 Template → AI → Word → Contract 生成流水线。新增模板中心(docxtpl 管理 Word 模板 + {{variable}} 自动解析)+ Generation Agent(手写 ReAct,4 个无状态 Tool:模板查询/RAG 检索/AI 条款生成/规则校验)+ Word 渲染(docxtpl 保留样式)+ 生成产物自动创建合同进入合同管理中心,形成"生成→解析→审核"闭环;
> v0.8.1 Sprint 6 补充:模板中心增加 `version` 字段(同名模板多版本管理)+ `rule_validation_tool` 重命名为 `contract_rule_tool`(统一 Tool 命名规范,明确缺失字段+风险条款校验职责),增量迁移不破坏现有数据。
> v0.9.0 Sprint 7:企业级 AI 招投标管理系统(Enterprise Bid Management)— 构建完整的招标文件 → 结构化 Requirement → Bid Agent → 投标方案 → Word 文件闭环。新增 Bid Pipeline(复用 Sprint 3,15 字段 Requirement 抽取)+ Proposal Agent(手写 ReAct,5 个无状态 Tool:需求读取/企业知识检索/企业资料/章节生成/合规校验)+ Word 渲染(复用 Sprint 6 docxtpl)+ 4 张新表 + knowledge_type 扩展(区分企业资料/招标/合同/案例/资质),前端新增 Bid Management 菜单(6 页面)。未修改 Sprint 3~6 任何核心代码。
> v0.9.1 Sprint 7.1:Bid 企业级增强 — 新增 (1)Requirement Context Builder(复用 Sprint 4 Retriever,4 槽位检索企业知识库构建 RAG Context);(2)Requirement Trace(字段来源 4 字段:page_number/chunk_id/confidence/source_text,前端可点击查看);(3)Requirement Version(version,重新解析自增);(4)Requirement Review(需求审核状态 draft/reviewing/approved,Bid Agent 仅读取 approved);(5)Bid References(proposal_sections.references 4 字段与 Sprint 5 统一);(6)Tool Statistics & Trace(tool_call_count/成功率/时长 + trace_summary 与 Sprint 5 统一);+ 3 个新审核 API。Sprint 3~6 核心逻辑零修改,API/DB 完全向后兼容。
> **v1.0.0 Sprint 8:Enterprise AI 企业级能力 — 新增 (1)Redis Cache(CacheService,RAG/Review/Generation 缓存 + namespace:SHA1 Key + 内存 LRU 降级,异常不阻断);(2)AIRequestLog(contextvars token 统计 + 3 个 Agent/RAG 的 log_agent_run 钩子 + ai_log_service,失败仅 warning);(3)OperationAudit(audit_middleware + AUDIT_RULES 声明式,重点记录登录/合同上传/审核/生成/知识库/投标 11 类操作,异常不阻断);(4)PromptTemplate(name/version/status DB 管理,CRUD + activate,6 类 Prompt 支持;load_prompt:DB active → .md → 默认 prompt 三级回退,DB 故障不影响 Sprint 0~7);(5)AI Evaluation(evaluation_service + evaluation_reports,从日志聚合 RAG/Agent/Tool/成本/操作 5 类指标,admin 接口 + 持久化快照)。新增 4 张表 + 4 个 Service + 21 个新接口,Sprint 0~7 核心零修改,API 完全向后兼容。**

---

## 项目简介

智能合同与投标管理平台是一套基于人工智能的企业级合同与投标管理系统。当前版本已具备合同智能分析能力 + 用户身份认证能力,并将逐步演进为包含合同生命周期管理、RAG 知识库、合同审核 Agent、投标文件智能处理的一体化平台。

v0.2.0 验证并保留的核心 AI 能力:

- **PDF 文本提取**:pdfplumber 提取有文字层 PDF 的文本
- **图片 OCR 识别**:DeepSeek Vision API 识别图片中的合同文字
- **合同字段提取**:DeepSeek Chat API + LangChain 智能提取合同关键字段(名称/甲方/乙方/金额/签署日期)
- **结果展示**:Flask + Jinja2 + Bootstrap 5 前端页面

v0.3.0 新增用户认证能力:

- **用户注册 / 登录**:`/api/v1/auth/register`、`/api/v1/auth/login`
- **JWT 认证**:Flask-JWT-Extended,登录返回 access_token
- **当前用户信息**:`/api/v1/auth/profile`(需 JWT)
- **角色控制**:`@role_required("admin","contract_manager")` 装饰器,支持 admin / contract_manager / employee 三角色
- **密码安全**:Werkzeug hash 存储,禁止明文;响应不泄露 password_hash

v0.4.0 新增合同生命周期管理能力:

- **合同上传**:`POST /api/v1/contracts/upload`(需 JWT),保存文件 + 建记录 + 复用已有 AI 分析流程
- **合同列表**:`GET /api/v1/contracts`(需 JWT),分页 / 关键字 / 状态 / 创建人过滤
- **合同详情**:`GET /api/v1/contracts/{id}`(需 JWT),含创建人 / 状态 / 文件信息 / AI 分析结果
- **状态流转**:`PATCH /api/v1/contracts/{id}/status`(需 admin/contract_manager),状态机 draft→reviewed→archived
- **权限隔离**:employee 仅可见自己合同(他人合同返 404 防枚举)
- **文件管理**:统一 `uploads/contracts/{uuid}.ext`,UUID 命名;DB 存路径,响应不暴露

v0.4.0 新增 Admin Console 前端(Phase A + Phase B):

- **企业级后台框架**:Vue3 + Vite + Element Plus + Vue Router + Pinia + Axios,从零构建,不引入第三方后台模板
- **Progressive Admin Design**:只开发当前业务页面,不创建未来菜单 / 空白页 / 占位页
- **登录认证**:JWT 持久化(localStorage)+ 路由守卫 + 401 自动跳登录
- **后台布局**:Header + Sidebar + Main,角色标签 + 退出登录
- **合同管理页面**:合同列表(分页/搜索/状态过滤)+ 上传合同(PDF + AI 分析)+ 合同详情(状态流转 + AI 结果展示)
- **我的账户页面**:用户信息 + Token 信息 + 退出登录(RC 新增)
- **权限控制**:前端根据角色隐藏状态流转按钮(employee 隐藏),后端真正校验
- **CORS 跨域**:Flask-CORS 仅开放 `/api/*`,Origin 白名单预留 `.env`(不用 `*`)

v0.5.0 新增 Document Pipeline 能力(Sprint 3):

- **Stage 架构 Pipeline**:`extract → ocr → clean → chunk → llm → save` 六个职责单一的 Stage,通过 `PipelineContext` 传递数据,Stage 间不直接互相调用
- **任务化追踪**:每次分析创建独立 `AnalysisTask`(`task_no` / `status` / `current_stage` / `stages_log`),实时记录每个 Stage 的耗时、状态与元数据
- **结构化字段存储**:新增 `contract_fields` 表,字段级 `confidence` + `source_text`,替代 Sprint 2 的 `analysis_result` JSON 列;支持 8 字段(`contract_no` / `contract_name` / `party_a` / `party_b` / `amount` / `sign_date` / `payment_method` / `valid_period`)
- **文档元数据解耦**:新增 `documents` 表,文件 + 提取文本与 `contracts` 解耦;`text_content` 落库支持失败重跑免重新 OCR
- **LLM 结构化输出**:Prompt 从代码剥离版本化管理(`prompts/contract_extract_v1.md`),LLM 必须输出 8 字段 JSON,缺失字段返回 `null`,**禁止编造**
- **触发方式变更**:上传不再自动触发 AI,改为详情页点"开始分析"按钮手动触发(`analysis_status=pending` → `completed` / `failed`)
- **向后兼容**:Sprint 2 旧合同 `analysis_result` JSON 列保留(只读),字段接口降级读取并补齐为 8 字段
- **3 个新接口**:`POST /api/v1/contracts/{id}/analysis`(触发分析)、`GET /api/v1/analysis/{task_id}`(查询任务)、`GET /api/v1/contracts/{id}/fields`(获取字段)
- **前端详情页升级**:AI 分析任务进度(6 个 Stage 状态)+ 结构化字段表格(8 字段 + confidence 进度条 + 来源文本)+ "开始分析 / 重新分析"按钮 + 数据来源标识

v0.6.0 新增知识管理与 RAG 基础能力(Sprint 4):

- **Knowledge Layer 五层解耦**:`loader → parser → chunk → embedding → vectorstore → retriever`,各层通过抽象基类 + 依赖注入组装,不直接相互调用
- **知识文档上传**:`POST /api/v1/knowledge/upload`(需 admin/contract_manager),支持 pdf/docx/txt,同步完成 解析→Chunk→Embedding→FAISS→持久化
- **Chunk 持久化 + Metadata + Overlap**:新增 `knowledge_documents` / `knowledge_chunks` 两表;Chunk 含 `page_number`/`start_offset`/`end_offset`/`token_count`/`metadata` 全字段;相邻 Chunk overlap=200 字符(解决 Sprint 3 Final Check 三大问题)
- **Embedding**:sentence-transformers + BAAI/bge-small-zh-v1.5(512 维,归一化向量;禁止 OpenAI Embedding);懒加载 + 本地物化下载(规避 Windows 符号链接问题)
- **Vector Store**:FAISS IndexFlatIP + IndexIDMap2(支持 add/search/delete/save/load;vector_id 自增 + meta.json 持久化)
- **Retriever**:TopK=5 + score_threshold=0.35(归一化余弦);预留 Hybrid Search 扩展点
- **RAG 问答**:`POST /api/v1/rag/query`(需 JWT),检索→context 构建→DeepSeek 生成(temperature=0.0,忠实检索内容);返回 answer + references + score;空知识库/无命中不调 LLM
- **版本化 Prompt**:`prompts/rag_answer.md`(v1.0:仅依据检索内容 / 禁止编造 / 未命中明确说明 / 保留 `[文档n]` 引用)
- **5 个新接口**:`/knowledge/upload`、`GET /knowledge`、`GET /knowledge/{id}`、`DELETE /knowledge/{id}`、`POST /rag/query`
- **前端知识库管理**:知识文档列表(分页/过滤/Embedding 状态)+ 上传知识 + 知识详情 + **RAG Playground**(用户问题 + 命中 Chunk + 相似度进度条 + LLM 回答 + 引用来源)

v0.7.0 新增合同审核 Agent 能力(Sprint 5):

- **手写 ReAct Agent**(不引入 LangGraph/Agent 框架):LLM 决策(选 Tool / final_report)→ Tool 执行 → 观察入 ctx → 再决策;JSON 解析容错(去 Markdown 包裹 + 平衡括号匹配 + 单轮重试);LLM 失败 / 迭代上限走 `risk_rule_tool` 兜底
- **3 个无状态 Tool**:`contract_field_tool`(复用 Sprint 3 `analysis_service`)+ `knowledge_search_tool`(复用 Sprint 4 Retriever,返回 document_title / chunk_id / page_number / score)+ `risk_rule_tool`(11 条确定性规则覆盖付款 / 金额 / 期限 / 关键条款缺失 4 类风险)
- **审核报告持久化**:新增 `review_reports` 表(review_no / status / risk_level / risks JSON / tool_calls_log 审计轨迹 / iterations / llm_error)
- **4 个新接口**:`POST /api/v1/contracts/{id}/review`(触发审核,admin/contract_manager)、`GET /api/v1/contracts/{id}/reviews`(合同审核历史)、`GET /api/v1/reviews`(全局列表 + risk_level/status 过滤)、`GET /api/v1/reviews/{id}`(详情含 risks / tool_calls_log)
- **前端审核页面**:`ReviewList`(分页/过滤/风险标签)+ `ReviewDetail`(总体风险等级 + 风险列表 + 依据 + 建议 + 知识库引用来源 + Agent 工具调用轨迹)+ 合同详情页"AI 风险审核"触发按钮

v0.7.1 Agent 企业级可观测增强(Sprint 5 Final):

- **关键 Bug 修复**:修复 `ChatPromptTemplate` 将 Prompt 中 JSON 示例的 `{}` 误认为模板变量导致 LLM 无法调用的 bug,Agent 现在真正走完整 ReAct 流程(Thought → Action → Observation → Final)
- **Agent Trace**:每步记录 12 字段(step / thought / decision / action / tool_name / tool_input / observation / start_time / end_time / duration_ms / status / error_message),落库 `review_reports.agent_trace`
- **Tool Observability**:3 个 Tool 的调用次数 / 成功 / 失败 / 总耗时 / 最后错误,通过 `BaseTool.safe_run` 统一记录
- **LLM 容错**:7 类错误分类(timeout / rate_limit / server_error / network / auth / framework / json_parse / unknown)+ 超时控制(LLM_TIMEOUT=30s)+ 自动降级 RiskRuleTool
- **Agent 安全控制**:`MAX_AGENT_ITERATIONS` 从 config 读取(默认 5),超限生成 Iteration Exceeded 降级报告
- **Trace API**:新增 `GET /api/v1/reviews/{id}/trace` 接口
- **前端 Timeline**:ReviewDetail 页新增 Agent 执行过程 Timeline(🧠 Thought → 📌 Decision → 🔧 Action → 📄 Observation → ⏱ Duration → ✅ Status)+ 汇总统计条 + LLM 降级提示

v0.8.0 新增 AI 合同自动生成系统能力(Sprint 6):

- **模板中心**:Word 模板上传(`.docx`)+ `{{variable}}` 占位符自动解析(docxtpl `get_undeclared_template_variables`)+ 启停管理 + 权限控制(admin/manager 维护,employee 仅使用)
- **Contract Generation Pipeline**:模板选择 → 用户填写变量 → RAG 检索企业规范 → AI 补充缺失条款 → 规则校验 → Word 渲染 → 保存生成记录 → 自动创建合同(同步执行,不引入 Celery/Redis)
- **Generation Agent**(手写 ReAct,复用 Sprint 5 思想):4 个无状态 Tool — `template_tool`(模板变量查询)/ `knowledge_search_tool`(复用 Sprint 4 RAG)/ `clause_generation_tool`(调 DeepSeek 生成付款/违约/保密/知识产权/售后条款)/ `contract_rule_tool`(确定性规则校验:缺失字段 + 风险条款,不调 LLM,v0.8.1 由 `rule_validation_tool` 重命名);LLM 失败走兜底(无 AI 条款仍渲染 Word)
- **Word 渲染**:docxtpl + python-docx,保留模板原生样式(字体/表格/页眉页脚),导出 `.docx`,UUID 命名存 `uploads/generated/`
- **Generation Trace**:完整记录 Agent 执行过程(模板选择 → RAG 检索 → 条款生成 → 校验),每步 12 字段,落库 `generated_contracts.agent_trace`;前端 GenerationDetail 页 Timeline 展示
- **集成闭环**:生成产物自动创建 Contract 记录(`status=draft`, `analysis_status=pending`),进入合同管理中心,可继续触发 Sprint 3 AI 解析与 Sprint 5 合同审核,形成 "生成→解析→审核" 闭环
- **2 张新表**:`contract_templates`(15 字段,模板元信息 + 变量 JSON + version 版本管理)+ `generated_contracts`(23 字段,生成记录 + clauses/references/trace)
- **11 个新接口**:`/api/v1/templates`(5 接口:列表/上传/详情/启停/删除)+ `/api/v1/generation`(5 接口:预览/生成/历史/详情/Trace)+ `/api/v1/generated/{id}/download`(Word 下载)
- **前端 6 个新页面**:`TemplateList`(模板列表)+ `TemplateUpload`(上传+变量预览)+ `TemplateDetail`(变量清单)+ `GenerationCreate`(三步生成:选模板→动态变量表单→预览/生成)+ `GenerationHistory`(生成记录)+ `GenerationDetail`(AI 条款 + RAG 引用 + 校验 + Trace Timeline + 下载)

v0.9.0 新增企业级 AI 招投标管理能力(Sprint 7):

- **Bid Pipeline**(复用 Sprint 3):招标文件 → 类型检测 → PDF 文本提取(pdfplumber)/ 图片 OCR(DeepSeek-VL)→ 文本清洗 → Chunk 切分(SemanticChunker)→ LLM 抽 15 字段 Requirement JSON;`text_content` 落库支持失败重跑省算力
- **15 字段 Requirement**:`project_name` / `tender_org` / `project_location` / `budget` / `deadline` / `duration` / `delivery_requirements` / `technical_requirements[]` / `qualification_requirements[]` / `scoring_criteria[]` / `bid_opening_time` / `bid_validity` / `payment_terms` / `contact` / `other`;含质量指标 `confidence`(LLM 自评均值)/ `field_count` / `missing_count`
- **Proposal Agent**(手写 ReAct,复用 Sprint 5/6 思想):5 个无状态 Tool — `requirement_tool`(读取 15 字段)/ `bid_knowledge_search_tool`(复用 Sprint 4 retriever,按 `knowledge_type` 后过滤)/ `company_profile_tool`(企业资料)/ `proposal_section_tool`(调 DeepSeek 生成章节)/ `compliance_rule_tool`(必填章节+关键字段校验,镜像 Sprint 6);LLM 失败走兜底(规则骨架仍渲染 Word)
- **完整 Trace**:Thought / Decision / Action / Observation / Duration / Status(12 字段/步),落库 `generated_proposals.agent_trace`;前端 ProposalDetail 页 Timeline 展示(复用 Sprint 6 Timeline 组件)
- **Word 投标文件**:复用 Sprint 6 `docxtpl` + `python-docx`,根据模板 + 企业资料 + AI 生成章节(technical / commercial / responsive / qualification / summary)渲染 `.docx`,UUID 命名存 `uploads/bids/proposals/`
- **knowledge_type 扩展**:`knowledge_documents` 新增 `knowledge_type` 字段(增量迁移,旧文档回填 `general`),6 种取值(general / contract / bid / company / case / qualification);**未新增第二套 Embedding/VectorStore**,仅上层按类型过滤
- **4 张新表 + 1 个扩展字段**:`bid_documents`(招标文件)/ `bid_requirements`(15 字段需求,1:1)/ `generated_proposals`(生成记录,镜像 generated_contracts)/ `proposal_sections`(章节,1:N)+ `knowledge_documents.knowledge_type`(扩展);**不修改** Sprint 3~6 任何表
- **11 个新接口**:`/api/v1/bids`(7 接口:上传/列表/详情/删除/重解析/需求查询/生成投标)+ `/api/v1/proposals`(4 接口:列表/详情/Trace/下载)
- **前端 6 个新页面**:`BidList`(招标文件列表)+ `BidUpload`(上传)+ `BidDetail`(详情+15 字段 Requirement)+ `BidRequirement`(需求分析)+ `ProposalList`(生成记录列表)+ `ProposalCreate`(生成参数)+ `ProposalDetail`(章节内容 + RAG 引用 + 校验 + Trace Timeline + 下载)

---

## 当前架构(v1.0.0)

采用 **Application Factory + Blueprint + 分层架构**:

```
请求
 ↓
api/contract/routes.py          (contract_bp:合同上传页 HTML;contract_api_bp:/api/v1/contracts + /analysis + /fields + /review,Sprint 2/3/5)
api/analysis/routes.py         (analysis_bp:/api/v1/analysis/{task_id},Sprint 3 新增)
api/knowledge/routes.py        (knowledge_bp:/api/v1/knowledge + rag_bp:/api/v1/rag,Sprint 4 新增)
api/review/routes.py           (review_bp:/api/v1/reviews,Sprint 5 新增)
api/templates/routes.py        (template_bp:/api/v1/templates,Sprint 6 新增)
api/generation/routes.py       (generation_bp:/api/v1/generation + generated_download_bp:/api/v1/generated,Sprint 6 新增)
api/bid/routes.py              (bid_bp:/api/v1/bids + proposal_bp:/api/v1/proposals,Sprint 7 新增)
api/system/routes.py           (Blueprint:/api/v1/health JSON)
api/auth/routes.py             (Blueprint:/api/v1/auth JSON,Sprint 1)
 ↓
services/analysis_service.py   (Service:分析任务编排 触发/查询/字段,Sprint 3 新增;被 Agent 只读复用)
services/contract_service.py   (Service:合同生命周期管理,Sprint 2;Sprint 6 新增 create_contract_from_generation)
services/document_service.py   (Service:legacy 上传→PDF/OCR→字段 编排;底层函数被 Pipeline 复用)
services/review_service.py     (Service:合同审核 触发/查询/列表,Sprint 5 新增)
services/template_service.py   (Service:模板管理 上传/列表/详情/启停/删除,Sprint 6 新增)
services/generation_service.py (Service:合同生成编排 预览/生成/历史/Trace/下载,Sprint 6 新增)
services/bid_service.py        (Service:招标业务 上传/落库/Pipeline 调度/列表/详情/删除守卫/重解析/需求查询,Sprint 7 新增)
services/proposal_service.py   (Service:投标业务 Agent 调度/Word 渲染/单事务落库/Trace/下载,Sprint 7 新增)
services/auth_service.py       (Service:注册/登录/profile,Sprint 1)
 ↓
ai/pipeline/runner.py          (Pipeline 编排器:状态机驱动 Stage 执行,Sprint 3 新增)
ai/pipeline/stages/*.py        (6 个 Stage:extract/ocr/clean/chunk/llm/save,Sprint 3 新增)
ai/pipeline/prompts/*.md       (版本化 Prompt,Sprint 3 新增)
ai/agent/contract_review_agent.py (ReAct Agent:LLM 决策 + Tool 执行,Sprint 5 新增)
ai/agent/tools/*.py            (3 个 Tool:字段查询/RAG 检索/规则检查,Sprint 5 新增)
ai/agent/prompts/*.md          (Agent Prompt v1,Sprint 5 新增)
ai/generation/generation_agent.py  (Generation Agent:ReAct 决策 + 4 Tool,Sprint 6 新增)
ai/generation/tools/*.py       (4 个 Tool:模板查询/RAG检索/条款生成/规则校验,Sprint 6 新增)
ai/generation/word_renderer.py (Word 渲染:docxtpl + python-docx,Sprint 6 新增)
ai/generation/prompts/*.md     (Generation Agent Prompt v1 + 条款生成 Prompt v1,Sprint 6 新增)
ai/bid/pipeline.py             (Bid Pipeline:复用 Sprint 3 提取 + LLM 抽 15 字段,Sprint 7 新增)
ai/bid/proposal_agent.py       (Proposal Agent:ReAct 决策 + 5 Tool,Sprint 7 新增)
ai/bid/tools/*.py              (5 个 Tool:需求读取/企业知识检索/企业资料/章节生成/合规校验,Sprint 7 新增)
ai/bid/proposal_renderer.py    (投标 Word 渲染:复用 Sprint 6 docxtpl + python-docx,Sprint 7 新增)
ai/bid/prompts/*.md            (bid_requirement_v1 + bid_proposal_v1 + proposal_section_v1,Sprint 7 新增)
ai/ocr/ocr_service.py           (AI 层:DeepSeek Vision OCR,被 OcrStage 复用)
ai/llm/deepseek_service.py     (AI 层:legacy DeepSeek 合同字段提取)
 ↓
knowledge/services/            (knowledge_service + rag_service + vector_store_registry,Sprint 4 新增;被 Agent 只读复用)
knowledge/loader/              (Pdf/Docx/Txt Loader,Sprint 4 新增)
knowledge/parser/              (parse_document + page_map,Sprint 4 新增)
knowledge/chunk/               (SemanticChunker:chunk_size=500, overlap=200,Sprint 4 新增)
knowledge/embedding/           (SentenceTransformerEmbedding:bge-small-zh-v1.5,Sprint 4 新增)
knowledge/vectorstore/         (FaissVectorStore:IndexFlatIP + IndexIDMap2,Sprint 4 新增)
knowledge/retriever/           (DenseRetriever:TopK + 阈值,Sprint 4 新增)
knowledge/prompts/             (rag_answer.md Prompt v1.0,Sprint 4 新增)
 ↓
models/user.py                 (Model:users 表,Sprint 1)
models/contract.py             (Model:contracts 表 + 状态机,Sprint 2)
models/document.py             (Model:documents 表,Sprint 3 新增)
models/analysis_task.py        (Model:analysis_tasks 表,Sprint 3 新增)
models/contract_field.py       (Model:contract_fields 表,Sprint 3 新增)
models/knowledge_document.py   (Model:knowledge_documents 表,Sprint 4 新增)
models/knowledge_chunk.py      (Model:knowledge_chunks 表,Sprint 4 新增)
models/review_report.py        (Model:review_reports 表,Sprint 5 新增)
models/contract_template.py    (Model:contract_templates 表,Sprint 6 新增)
models/generated_contract.py   (Model:generated_contracts 表,Sprint 6 新增)
models/bid_document.py         (Model:bid_documents 表,Sprint 7 新增)
models/bid_requirement.py      (Model:bid_requirements 表 15 字段,Sprint 7 新增)
models/generated_proposal.py   (Model:generated_proposals 表,Sprint 7 新增)
models/proposal_section.py     (Model:proposal_sections 表,Sprint 7 新增)
 ↓
decorators/role_required.py    (角色控制,Sprint 1)
extensions/ + config/ + utils/  (db+jwt+logger / 配置 / 工具)
```

**职责约束**:API 层不直接调用 OCR/LLM、不直接访问数据库、不直接生成 JWT;Service 层不渲染模板;AI 层不访问 HTTP 请求对象;Pipeline Stage 间不直接互相调用,仅通过 `PipelineContext` 传递数据。

### 基础设施(v0.2.1)

| 能力 | 模块 | 说明 |
|------|------|------|
| 统一 API 响应 | `app/utils/response.py` | `success()` / `error()`,格式 `{code, message, data}` |
| 统一异常处理 | `app/utils/exceptions.py` | `AppException` + 全局 ErrorHandler,禁止 `return str(e)` |
| 日志系统 | `app/extensions/logger.py` | logging + 文件轮转,输出 `logs/app.log` |
| 数据库(初始化) | `app/extensions/db.py` | SQLAlchemy `db.init_app(app)` |
| 健康检查 | `GET /api/v1/health` | 返回 `{code:200, message:"success", data:{status:"ok"}}` |

### 用户认证能力(v0.3.0 新增)

| 能力 | 模块 | 说明 |
|------|------|------|
| 用户模型 | `app/models/user.py` | users 表(id/username/password_hash/role/时间戳),密码 Werkzeug hash |
| JWT 扩展 | `app/extensions/jwt.py` | Flask-JWT-Extended,异常统一回调(401) |
| 认证服务 | `app/services/auth_service.py` | 注册 / 登录 / profile,JWT claims 携带 role |
| 认证接口 | `app/api/auth/routes.py` | `/api/v1/auth/{register,login,profile}` |
| 角色控制 | `app/decorators/role_required.py` | `@role_required("admin","contract_manager")`,不符抛 403 |
| 数据库建表 | `create_app()` 内 `db.create_all()` | Sprint 1 起自动建 users 表;Sprint 2 起 contracts 表;Sprint 3 起 documents/analysis_tasks/contract_fields 表 |

### 合同生命周期管理能力(v0.4.0 新增)

| 能力 | 模块 | 说明 |
|------|------|------|
| 合同模型 | `app/models/contract.py` | contracts 表(14 字段)+ 状态机(`draft`/`reviewed`/`archived`)+ User 一对多(backref) |
| 合同业务服务 | `app/services/contract_service.py` | 创建 / 列表 / 详情 / 状态更新;权限过滤(employee 隔离);AI 复用 |
| 合同 RESTful API | `app/api/contract/routes.py`(`contract_api_bp`) | `/api/v1/contracts` 下 4 个接口 |
| AI 复用函数 | `app/services/document_service.py`(`analyze_document`) | 复用 OCR / DeepSeek,不修改既有函数 |
| 文件管理 | `uploads/contracts/{uuid}.ext` | UUID 命名;DB 存 `file_path`;响应不暴露路径 |

### Document Pipeline 能力(v0.5.0 新增)

| 能力 | 模块 | 说明 |
|------|------|------|
| 文档模型 | `app/models/document.py` | documents 表:文件元信息 + 提取文本(`text_content` 落库,失败重跑免重新 OCR) |
| 任务模型 | `app/models/analysis_task.py` | analysis_tasks 表:`task_no` / `status` / `current_stage` / `stages_log`(JSON) |
| 字段模型 | `app/models/contract_field.py` | contract_fields 表:8 字段 + 字段级 `confidence` + `source_text` |
| Pipeline 编排器 | `app/ai/pipeline/runner.py` | 状态机驱动 Stage 执行,实时更新 `task.current_stage` 与 `stages_log` |
| Stage 架构 | `app/ai/pipeline/stages/*.py` | 6 个 Stage:extract / ocr / clean / chunk / llm / save(职责单一) |
| 版本化 Prompt | `app/ai/pipeline/prompts/contract_extract_v1.md` | LLM 字段提取 Prompt 从代码剥离,版本化管理(v1.0) |
| 分析业务服务 | `app/services/analysis_service.py` | 触发分析 / 查询任务 / 获取字段(含 Sprint 2 旧合同降级逻辑) |
| 分析任务 API | `app/api/analysis/routes.py`(`analysis_bp`) | `GET /api/v1/analysis/{task_id}` |
| 合同分析 / 字段 API | `app/api/contract/routes.py`(`contract_api_bp`) | `POST /contracts/{id}/analysis` + `GET /contracts/{id}/fields` |
| 向后兼容 | `analysis_service.get_contract_fields` | 优先 `contract_fields` 表,降级读 `analysis_result` JSON 列(8 字段补 null) |

### 知识管理与 RAG 能力(v0.6.0 新增)

| 能力 | 模块 | 说明 |
|------|------|------|
| 知识文档模型 | `app/models/knowledge_document.py` | knowledge_documents 表:文档元信息 + embedding_status + vector_indexed + 软删 |
| 知识 Chunk 模型 | `app/models/knowledge_chunk.py` | knowledge_chunks 表:持久化 Chunk + metadata + offset + vector_id(解决 Sprint 3 三大问题) |
| Knowledge Layer | `app/knowledge/`(loader/parser/chunk/embedding/vectorstore/retriever) | 五层解耦,抽象基类 + 依赖注入,不直接相互调用 |
| 语义切分器 | `app/knowledge/chunk/semantic_chunker.py` | 递归字符切分:chunk_size=500, overlap=200, min_chunk_size=100;含 page_number/offset/token_count/metadata |
| Embedding | `app/knowledge/embedding/sentence_transformer_embedding.py` | BAAI/bge-small-zh-v1.5(512 维,归一化);懒加载 + 本地物化下载 |
| Vector Store | `app/knowledge/vectorstore/faiss_store.py` | FAISS IndexFlatIP + IndexIDMap2:add/search/delete/save/load;meta.json 持久化 |
| Retriever | `app/knowledge/retriever/dense_retriever.py` | TopK=5 + score_threshold=0.35;预留 Hybrid Search 扩展 |
| RAG Prompt | `app/knowledge/prompts/rag_answer.md` | Prompt v1.0:仅依据检索内容 / 禁止编造 / 保留 `[文档n]` 引用 |
| 知识业务服务 | `app/knowledge/services/knowledge_service.py` | 上传 / 列表 / 详情 / 删除(软删 + FAISS 移除) |
| RAG 业务服务 | `app/knowledge/services/rag_service.py` | 检索 → context 构建 → DeepSeek → Answer + References |
| 组件注册表 | `app/knowledge/services/vector_store_registry.py` | Embedding/VectorStore/Retriever 单例 + 启动加载 FAISS + DI 组装 |
| 知识库 API | `app/knowledge/api/routes.py`(`knowledge_bp` + `rag_bp`) | `/api/v1/knowledge` 4 接口 + `/api/v1/rag/query` 1 接口 |

### AI 招投标管理能力(v0.9.0 Sprint 7 新增)

| 能力 | 模块 | 说明 |
|------|------|------|
| 招标文档模型 | `app/models/bid_document.py` | bid_documents 表:招标文件 + 提取文本 + parse_status 状态机 + 删除守卫 |
| 招标需求模型 | `app/models/bid_requirement.py` | bid_requirements 表:15 字段 Requirement JSON + confidence + field_count/missing_count(1:1) |
| 投标生成记录模型 | `app/models/generated_proposal.py` | generated_proposals 表(镜像 generated_contracts):agent_trace / trace_summary / rag_references |
| 投标章节模型 | `app/models/proposal_section.py` | proposal_sections 表:5 章节类型(technical/commercial/responsive/qualification/summary)+ source(ai/template/rule) |
| Bid Pipeline | `app/ai/bid/pipeline.py` + `requirement_extractor.py` | 复用 Sprint 3 提取/OCR/清洗/Chunk → LLM 抽 15 字段 Requirement |
| Proposal Agent | `app/ai/bid/proposal_agent.py` | 手写 ReAct,5 个无状态 Tool,MAX_ITERATIONS=5,LLM 失败走兜底 |
| Bid Agent Tools | `app/ai/bid/tools/*.py` | 5 个 Tool:requirement / bid_knowledge_search / company_profile / proposal_section / compliance_rule |
| 投标 Word 渲染 | `app/ai/bid/proposal_renderer.py` | 复用 Sprint 6 docxtpl + python-docx,渲染 5 章节投标文件 |
| 招标业务服务 | `app/services/bid_service.py` | 上传/落库/Pipeline 调度/列表/详情/删除守卫/重解析/需求查询 |
| 投标业务服务 | `app/services/proposal_service.py` | Agent 调度/Word 渲染/单事务落库/Trace 查询/文件下载 |
| knowledge_type 扩展 | `migrations/sprint7_add_knowledge_type.py` | knowledge_documents 增量列(6 取值),旧文档回填 general,向后兼容 |
| 招标/投标 API | `app/api/bid/routes.py`(`bid_bp` + `proposal_bp`) | `/api/v1/bids` 7 接口 + `/api/v1/proposals` 4 接口 |
| 版本化 Prompt | `prompts/bid_requirement_v1.md` + `bid_proposal_v1.md` + `proposal_section_v1.md` | Prompt 从代码剥离,版本化管理 |

---

## 目录结构

```
.
├── backend/                             # 工程化后端(v0.2.0,主开发目录)
│   ├── run.py                           # 入口:create_app() + app.run(:5001)
│   ├── requirements.txt                 # 后端依赖(版本= legacy + Sprint 1 认证 + Sprint 4 知识库依赖)
│   ├── .env.example                     # 配置示例(含 JWT + Embedding/VectorStore)
│   └── app/
│       ├── __init__.py                  # create_app() Application Factory(含 db.create_all / init_jwt / Blueprint 注册 / vector_store_registry.load)
│       ├── api/
│       │   ├── contract/routes.py       # contract_bp: GET/POST /(HTML);contract_api_bp: /api/v1/contracts + /analysis + /fields(Sprint 2/3)
│       │   ├── analysis/routes.py       # analysis_bp: /api/v1/analysis/{task_id}(Sprint 3 新增)
│       │   ├── knowledge/routes.py      # knowledge_bp + rag_bp: /api/v1/knowledge + /api/v1/rag(Sprint 4 新增)
│       │   ├── bid/routes.py            # bid_bp + proposal_bp: /api/v1/bids + /api/v1/proposals(Sprint 7 新增)
│       │   ├── system/routes.py        # Blueprint: /api/v1/health
│       │   └── auth/routes.py          # Blueprint: /api/v1/auth(Sprint 1)
│       ├── services/
│       │   ├── analysis_service.py     # 分析任务编排:触发/查询/字段(Sprint 3 新增)
│       │   ├── document_service.py     # PDF提取 + 上传编排;底层函数被 Pipeline 复用(Sprint 2)
│       │   ├── auth_service.py         # 注册/登录/profile(Sprint 1)
│       │   ├── contract_service.py     # 合同生命周期管理(Sprint 2)
│       │   ├── bid_service.py          # 招标业务(Sprint 7 新增)
│       │   └── proposal_service.py     # 投标业务(Sprint 7 新增)
│       ├── ai/
│       │   ├── pipeline/               # Document Pipeline(Sprint 3 新增)
│       │   │   ├── context.py          # PipelineContext 数据载体
│       │   │   ├── base.py             # BaseStage 抽象基类 + StageResult
│       │   │   ├── runner.py           # Pipeline 编排器(状态机驱动)
│       │   │   ├── stages/             # 6 个 Stage:extract/ocr/clean/chunk/llm/save
│       │   │   └── prompts/            # 版本化 Prompt(contract_extract_v1.md)
│       │   ├── ocr/ocr_service.py       # DeepSeek Vision OCR(被 OcrStage 复用)
│       │   ├── llm/deepseek_service.py  # legacy 合同字段提取
│       │   └── bid/                     # Bid Pipeline + Proposal Agent(Sprint 7 新增)
│       │       ├── pipeline.py          # Bid Pipeline:复用 Sprint 3 提取 + LLM 抽 15 字段
│       │       ├── proposal_agent.py    # Proposal Agent:ReAct 决策 + 5 Tool
│       │       ├── proposal_renderer.py # 投标 Word 渲染(复用 Sprint 6 docxtpl)
│       │       ├── tools/               # 5 个无状态 Tool
│       │       └── prompts/             # bid_requirement_v1 + bid_proposal_v1 + proposal_section_v1
│       ├── knowledge/                   # Knowledge Layer(Sprint 4 新增)
│       │   ├── api/routes.py           # knowledge_bp + rag_bp:知识管理 + RAG 问答
│       │   ├── services/               # knowledge_service + rag_service + vector_store_registry
│       │   ├── loader/                 # Pdf/Docx/Txt Loader(BaseLoader 抽象)
│       │   ├── parser/                 # parse_document + page_map + locate_page
│       │   ├── chunk/                  # Chunk 数据对象 + BaseChunker + SemanticChunker
│       │   ├── embedding/              # BaseEmbedding + SentenceTransformerEmbedding
│       │   ├── vectorstore/            # BaseVectorStore + FaissVectorStore
│       │   ├── retriever/              # BaseRetriever + DenseRetriever
│       │   └── prompts/                # rag_answer.md(Prompt v1.0)
│       ├── models/user.py              # users 表(Sprint 1)
│       ├── models/contract.py          # contracts 表 + 状态机(Sprint 2)
│       ├── models/document.py          # documents 表(Sprint 3 新增)
│       ├── models/analysis_task.py     # analysis_tasks 表(Sprint 3 新增)
│       ├── models/contract_field.py    # contract_fields 表(Sprint 3 新增)
│       ├── models/knowledge_document.py # knowledge_documents 表(Sprint 4 新增 / v0.9.0 增 knowledge_type)
│       ├── models/knowledge_chunk.py   # knowledge_chunks 表(Sprint 4 新增)
│       ├── models/bid_document.py      # bid_documents 表(Sprint 7 新增)
│       ├── models/bid_requirement.py   # bid_requirements 表 15 字段(Sprint 7 新增)
│       ├── models/generated_proposal.py # generated_proposals 表(Sprint 7 新增)
│       ├── models/proposal_section.py  # proposal_sections 表(Sprint 7 新增)
│       ├── decorators/role_required.py # @role_required()(Sprint 1)
│       ├── utils/                       # file_utils / text_utils / response / exceptions
│       ├── config/                      # settings.py 配置类(含 JWT + Embedding/VectorStore 配置)
│       ├── extensions/                  # db.py / jwt.py / logger.py
│   └── templates/index.html         # 前端页面(从 legacy 复制,UI 不变)
├── frontend/                            # Admin Console 前端(v0.4.0 Sprint 2 / v0.5.0 Sprint 3 / v0.6.0 Sprint 4 升级)
│   ├── package.json                    # 依赖与脚本(dev/build/preview)
│   ├── vite.config.js                  # Vite 配置(端口 5173,alias @ → src)
│   ├── .env.development                # VITE_API_BASE_URL=http://127.0.0.1:5001/api/v1
│   ├── .env.production                 # VITE_API_BASE_URL=/api/v1
│   └── src/
│       ├── main.js                     # 应用入口(Vue + Element Plus + Pinia + Router)
│       ├── api/                        # Axios 封装 + 业务 API(auth/contract/knowledge;含 triggerContractAnalysis/getAnalysisTask/getContractFields/uploadKnowledgeDocument/queryRag)
│       ├── components/                 # SidebarMenu + contract/StatusTag + knowledge/EmbeddingStatusTag
│       ├── layouts/AdminLayout.vue     # Header + Sidebar + Main
│       ├── pages/                      # Login / Dashboard / Profile / contract/{List,Upload,Detail} / knowledge/{KnowledgeList,KnowledgeUpload,KnowledgeDetail,RagPlayground} / bid/{BidList,BidUpload,BidDetail,BidRequirement,ProposalList,ProposalCreate,ProposalDetail}(Sprint 7)
│       ├── router/index.js             # 路由表 + 全局守卫(JWT + 角色控制 + meta.roles)
│       ├── store/auth.js               # Pinia 认证 store
│       ├── styles/index.css            # 全局样式重置
│       └── utils/                      # constants.js(TASK_STATUS/PIPELINE_STAGES/EMBEDDING_STATUS) / format.js
├── legacy/                              # v0.1.0 旧版 Demo(原样归档,可独立运行)
│   ├── app.py                           # 单文件 Flask Demo
│   ├── templates/index.html
│   ├── requirements.txt
│   └── README.md
├── docs/                                # 项目文档
│   ├── LEGACY_ANALYSIS.md               # 旧版 Demo 分析
│   ├── LEGACY_PREPARE_REPORT.md          # 旧版归档报告
│   ├── SPRINT0_MIGRATION_PLAN.md        # Sprint 0 迁移计划
│   ├── SPRINT0_REPORT.md                # Sprint 0 完成报告
│   ├── SPRINT0_RELEASE_REPORT.md        # Sprint 0 Release 报告
│   ├── SPRINT1_REPORT.md                # Sprint 1 完成报告
│   ├── SPRINT2_REPORT.md                # Sprint 2 完成报告
│   ├── SPRINT3_ANALYSIS.md              # Sprint 3 当前 AI 流程分析与迁移方案(Sprint 3 新增)
│   ├── SPRINT3_REPORT.md                # Sprint 3 完成报告(Sprint 3 新增)
│   ├── DEPENDENCY_REPORT.md             # 依赖检查报告
│   ├── API_DESIGN.md                    # API 设计文档(v0.5.0)
│   └── DATABASE_DESIGN.md              # 数据库设计文档(v0.5.0)
├── uploads/                             # 运行时上传目录(gitignore)
├── .env.example                         # legacy 用环境变量示例
├── .gitignore
├── README.md                            # 本文件
└── CHANGELOG.md                         # 更新日志
```

---

## 运行方式

### 方式一:工程化后端(推荐,v0.2.0)

```bash
cd backend
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env,填入 DEEPSEEK_API_KEY=你的真实API Key

# 启动
python run.py
```

访问地址:http://127.0.0.1:5001/

### 方式二:Admin Console 前端 + 后端联调(v1.0.0 推荐)

**前置**:先按"方式一"启动后端(端口 5001),并确保 `backend/.env` 中 `CORS_ORIGINS` 包含前端访问地址。

```bash
# 1. 启动后端(端口 5001)
cd backend
python run.py

# 2. 启动前端(端口 5173,新开终端)
cd frontend
npm install        # 首次需要安装依赖
npm run dev
```

浏览器访问:http://localhost:5173

**测试账号**(需先通过 `/api/v1/auth/register` 注册):

| 用户名 | 密码 | 角色 | 权限 |
|--------|------|------|------|
| admin | 123456 | admin | 全部权限(含合同审核) |
| manager | 123456 | contract_manager | 上传 / 查看 / 修改状态 / 合同审核 |
| employee | 123456 | employee | 上传 / 查看自己的合同(不可审核) |

**Admin Console 功能**:
- 登录页(JWT 认证,自动跳转 Dashboard)
- Dashboard(欢迎信息 + 系统版本 + 快捷入口)
- 合同管理(分页列表 + 关键字搜索 + 状态过滤)
- 上传合同(PDF/图片拖拽上传,上传后状态为"待分析",需在详情页手动触发分析)
- 合同详情(基本信息 + 文件信息 + 创建人 + **AI 分析任务进度(6 个 Stage)+ 结构化字段表格 + 状态流转 + AI 风险审核按钮**)
- 状态机(draft → reviewed → archived,admin/contract_manager 可操作)
- **Document Pipeline 触发**(v0.5.0):详情页"开始分析 / 重新分析"按钮,实时展示 `extract → ocr → clean → chunk → llm → save` 各 Stage 状态与耗时
- **知识库管理**(v0.6.0):知识文档列表 / 上传知识 / 知识详情 / RAG Playground
- **合同审核**(v0.7.0):审核报告列表(风险等级 + 状态过滤)+ 审核详情(总体风险等级 + 风险列表 + 依据 + 建议 + 知识库引用来源 + Agent 工具调用轨迹);合同详情页"AI 风险审核"按钮(仅 admin/contract_manager + 已完成 AI 分析)
- **模板中心**(v0.8.0):模板列表(分页/搜索/状态过滤)+ 上传模板(.docx + {{variable}} 自动解析预览)+ 模板详情(变量清单 + 元信息 + 启停)
- **合同生成**(v0.8.0):三步生成向导(选模板 → 动态变量表单 → 预览/正式生成)+ 生成记录列表 + 生成详情(AI 补充条款 + RAG 引用 + 校验结果 + Generation Trace Timeline + Word 下载)

> 前端架构详见 `docs/FRONTEND_ARCHITECTURE.md`。

### 数据库初始化

后端基于 Flask-SQLAlchemy,首次启动时在 `create_app()` 内自动执行 `db.create_all()` 创建全部数据表(users / contracts / contract_fields / knowledge_documents / knowledge_chunks / review_reports / contract_templates / generated_contracts / bid_documents / bid_requirements / generated_proposals / proposal_sections / prompt_templates / ai_request_logs / operation_logs / evaluation_reports 等 19 张表),无需手动建库。

```bash
cd backend
# 首次启动即自动建表
python run.py
```

数据库文件默认生成于 `backend/instance/app.db`(SQLite)。生产环境可通过 `SQLALCHEMY_DATABASE_URI` 切换 MySQL,建议使用 `migrations/` 下的增量迁移脚本演进表结构。

### 模型下载说明

Embedding 与 Rerank 模型使用 sentence-transformers / FlagEmbedding 本地加载,首次运行时自动从 HuggingFace 下载并缓存在本地:

| 用途 | 模型 | 说明 |
|------|------|------|
| Embedding | `BAAI/bge-small-zh-v1.5` | 512 维,中文优化,默认 `EMBEDDING_MODEL` |
| Rerank | `BAAI/bge-reranker-base` | 精排,`RERANK_ENABLED=true` 时启用 |

模型默认下载缓存目录 `backend/storage/models/`(离线环境可手动放入同名模型文件)。如需更换模型,修改 `backend/.env` 中的 `EMBEDDING_MODEL` / `RERANKER_MODEL`。

### AI Evaluation 使用方式

项目内置 AI 能力评估模块(Sprint 8.5),可对 RAG 问答 / 合同审核 Agent / AI 调用质量进行量化评估并生成报告:

```bash
# 1. 初始化评估知识库(首次执行,创建评估用测试文档)
cd backend && python -m scripts.init_evaluation_knowledge  # 或 cd scripts && python init_evaluation_knowledge.py

# 2. 执行完整评估(输出 reports/evaluation_summary.json)
python scripts/run_ai_evaluation.py

# 3. 前端查看评估结果(admin 登录)
#    http://localhost:5173/evaluation
```

评估报告持久化到 `evaluation_reports` 表,前端「AI 评估」页可查看最新摘要与历史报告。评估指标(RAG 命中率 / 回答相关度 / Agent 工具成功率 / Token 成本 / 操作失败率)与判定标准详见 `docs/SPRINT8_5_AI_EVALUATION_REPORT.md`。

### 认证接口示例(v0.3.0)

```bash
# 注册
curl -X POST http://127.0.0.1:5001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456","role":"admin"}'

# 登录(获取 access_token)
curl -X POST http://127.0.0.1:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'

# 获取当前用户(携带 JWT)
curl http://127.0.0.1:5001/api/v1/auth/profile \
  -H "Authorization: Bearer <access_token>"
```

### 合同管理接口示例(v0.4.0)

```bash
# 上传合同(需 JWT)
curl -X POST http://127.0.0.1:5001/api/v1/contracts/upload \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@合同.pdf" \
  -F "contract_type=采购合同" \
  -F "title=采购合同"

# 合同列表(分页 + 状态过滤)
curl "http://127.0.0.1:5001/api/v1/contracts?page=1&size=20&status=draft" \
  -H "Authorization: Bearer <access_token>"

# 合同详情
curl http://127.0.0.1:5001/api/v1/contracts/1 \
  -H "Authorization: Bearer <access_token>"

# 更新合同状态(需 admin/contract_manager)
curl -X PATCH http://127.0.0.1:5001/api/v1/contracts/1/status \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"status":"reviewed"}'
```

### Document Pipeline 接口示例(v0.5.0 Sprint 3)

```bash
# 触发合同分析(同步执行,超时 300s)
curl -X POST http://127.0.0.1:5001/api/v1/contracts/1/analysis \
  -H "Authorization: Bearer <access_token>"
# 返回:task(含 stages_log 各 Stage 状态/耗时)+ contract(analysis_status 已回写)

# 查询分析任务状态(历史回溯 / 未来异步轮询)
curl http://127.0.0.1:5001/api/v1/analysis/12 \
  -H "Authorization: Bearer <access_token>"

# 获取合同结构化字段(8 字段,优先 contract_fields 表,降级 analysis_result JSON)
curl http://127.0.0.1:5001/api/v1/contracts/1/fields \
  -H "Authorization: Bearer <access_token>"
```

> 完整接口文档见 `docs/API_DESIGN.md`(第八章 Document Pipeline 模块)。

---

## 环境变量

在 `backend/.env` 中配置(从 `backend/.env.example` 复制):

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key(必填) | — |
| `DEEPSEEK_API_BASE` | DeepSeek API 基础 URL | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` |
| `SECRET_KEY` | Flask 会话密钥(生产必须修改) | `supersecretkey` |
| `JWT_SECRET_KEY` | JWT 签名密钥(生产必须修改,v0.3.0) | `dev-jwt-secret-change-me-in-production` |
| `JWT_ACCESS_TOKEN_EXPIRES` | Access Token 有效期(秒) | `86400`(24 小时) |
| `SQLALCHEMY_DATABASE_URI` | 数据库连接串 | `sqlite:///instance/app.db` |
| `FLASK_ENV` | 运行环境 | `development` |
| `RAG_ANSWER_MODE` | RAG 回答模式:`generate`(LLM 生成)/ `extract`(句级抽取,生产推荐) | `generate` |
| `RAG_EXTRACT_TOP_N` / `RAG_EXTRACT_MIN_SIM` | extract 模式抽取句数 / 最小相似度 | `3` / `0.55` |
| `RETRIEVER_TOP_K` | RAG 检索返回 TopK | `5` |
| `REDIS_URL` / `CACHE_ENABLED` | Redis 缓存连接串 / 总开关(不可用时自动内存降级) | 空 / `true` |

> 完整配置项清单见 `backend/.env.example`(含 LLM 超时重试、Rerank 精排、Chunk 切分、AI 评估等全部参数说明)。

---

## 技术栈

| 模块 | 技术 |
|------|------|
| 后端框架 | Flask 2.3.3(Application Factory + Blueprint) |
| 数据库 ORM | Flask-SQLAlchemy 3.1.1 |
| 认证 | Flask-JWT-Extended 4.6.0(v0.3.0) |
| 密码哈希 | Werkzeug 2.3.7 |
| PDF 解析 | pdfplumber 0.10.2 |
| 图片处理 | Pillow 10.0.0 |
| OCR 识别 | DeepSeek Vision API |
| AI 框架 | langchain-openai 0.1.2 / langchain-core 0.1.53 |
| 大模型 | DeepSeek Chat API |
| **Document Pipeline** | **Stage 架构(extract/ocr/clean/chunk/llm/save)+ PipelineContext + 状态机驱动(v0.5.0)** |
| 前端框架(Admin Console) | Vue 3 + Vite + Element Plus + Pinia + Vue Router + Axios(v0.4.0) |
| 跨域处理 | Flask-CORS 4.0.0(仅 `/api/*`,Origin 白名单,v0.4.0) |
| 配置管理 | python-dotenv + config 模块;前端 .env.development / .env.production |

---

## 版本规划

| 版本 | 说明 | 状态 |
|------|------|------|
| v0.1.0 | 合同 AI 分析 Demo(单文件) | ✅ 已完成(归档于 `legacy/`) |
| v0.2.0 | 工程化重构(Application Factory + 分层) | ✅ 已完成 |
| v0.2.1 | Release Check(统一响应/异常/日志/db/health) | ✅ 已完成 |
| v0.3.0 | **用户认证系统(JWT + 角色控制 + users 表)** | ✅ 已完成(Sprint 1) |
| v0.4.0 | **合同生命周期管理(上传/列表/详情/状态机 + 权限控制 + contracts 表)+ Admin Console 前端(Vue3 + Element Plus)** | ✅ 已完成(Sprint 2) |
| v0.5.0 | **Document Pipeline(Stage 架构 + 任务化追踪 + 结构化字段 + Prompt 版本化)+ documents/analysis_tasks/contract_fields 三表** | ✅ 已完成(Sprint 3) |
| v0.6.0 | **Knowledge Layer(五层解耦)+ RAG 基础能力(FAISS + sentence-transformers + DeepSeek)+ knowledge_documents/knowledge_chunks 两表** | ✅ 已完成(Sprint 4) |
| v0.7.0 | **合同审核 Agent(手写 ReAct + 3 个无状态 Tool + review_reports 表)** | ✅ 已完成(Sprint 5) |
| v0.7.1 | **Agent 企业级可观测增强(Agent Trace + Tool Observability + LLM 容错)** | ✅ 已完成(Sprint 5 Final) |
| v0.8.0 | **AI 合同自动生成系统(Template → AI → Word → Contract Pipeline + Generation Agent + 4 Tool + contract_templates/generated_contracts 两表)** | ✅ 已完成(Sprint 6) |
| v0.9.0 | **企业级 AI 招投标管理系统(Bid Pipeline + Proposal Agent + 5 Tool + bid_documents/bid_requirements/generated_proposals/proposal_sections 四表 + knowledge_type 扩展)** | ✅ 已完成(Sprint 7) |
| v0.9.1 | **Bid 企业级增强(Requirement Context Builder / Trace / Version / Review / References / Tool Stats)** | ✅ 已完成(Sprint 7.1) |
| v1.0.0 | **Enterprise AI 企业级增强(Redis 缓存 / AI 调用日志 / 操作审计 / Prompt 数据库管理 / AI 评估 + 4 表)** | ✅ 已完成(Sprint 8) |
| v1.1+ | Docker 部署 / MinIO 对象存储 / 消息队列 / 数据分析 | 🚧 计划中 |

> 详见 `docs/API_DESIGN.md`、`docs/DATABASE_DESIGN.md`、`docs/FRONTEND_ARCHITECTURE.md`、`docs/V1.0.0_FINAL_RELEASE_CHECKLIST.md`、`docs/SPRINT8_5_AI_EVALUATION_REPORT.md`、`docs/SPRINT8_8_KB_RAG_ACCEPTANCE_REPORT.md`、`docs/SPRINT8_9_RAG_ANSWER_OPTIMIZATION_REPORT.md`、`docs/SPRINT8_9_PRODUCTION_REGRESSION_REPORT.md` 与 `CHANGELOG.md`。

---

## 许可证

MIT License
