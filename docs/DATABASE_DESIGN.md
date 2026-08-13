# 智能合同与投标管理平台 数据库设计文档

> **当前版本**:v1.0.0(Sprint 8 - Enterprise AI 企业级增强)
> **ORM**:SQLAlchemy(Flask-SQLAlchemy 3.1.1)
> **默认数据库**:SQLite(`backend/instance/app.db`)
> **生产建议**:MySQL(`mysql+pymysql://user:pass@localhost:3306/contract_platform`)
>
> **版本历史**:v0.3.0(users)→ v0.4.0(contracts)→ v0.5.0(documents/analysis_tasks/contract_fields)→ v0.6.0(knowledge_documents/knowledge_chunks)→ v0.7.0(review_reports)→ v0.8.0(contract_templates/generated_contracts)→ v0.9.0(bid_documents/bid_requirements/generated_proposals/proposal_sections + knowledge_type 扩展)→ v0.9.1(bid_requirements 版本/审核/字段来源 + proposal_sections references 统一 + 可观测性对齐)→ **v1.0.0(4 张新表:ai_request_logs / operation_logs / prompt_templates / evaluation_reports)**

---

## 一、设计规范

### 1.1 通用字段约定

所有业务表必须包含:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer (PK, autoincrement) | 主键 |
| created_time | DateTime | 创建时间(UTC,默认 `datetime.utcnow`) |
| updated_time | DateTime | 更新时间(UTC,`onupdate=datetime.utcnow`) |

### 1.2 命名约定

- 表名:复数小写(`users`、`contracts`、`bids`)
- 字段名:snake_case
- 外键:`{表名单数}_id`(如 `creator_id`)
- 索引:频繁查询字段建索引

### 1.3 数据库初始化

- 实例声明:`app/extensions/db.py` → `db = SQLAlchemy()`
- 初始化:`create_app()` 中 `db.init_app(app)`
- 建表:`create_app()` 内 `app.app_context()` + `db.create_all()`(Sprint 1 起)

> 当前为开发期自动建表;Sprint 2+ 将引入 Flask-Migrate(Alembic)做迁移管理。

---

## 二、users 表(v0.3.0 新增)

### 2.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| username | String(64) | NOT NULL, UNIQUE, INDEX | 用户名 |
| password_hash | String(255) | NOT NULL | 密码哈希(Werkzeug) |
| role | String(32) | NOT NULL, DEFAULT 'employee' | 角色(admin/contract_manager/employee) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 2.2 字段说明

#### id
- 主键,自增。
- 作为 JWT `identity`(签发时转字符串 `str(user.id)`)。

#### username
- 用户登录名,全局唯一。
- 应用层校验非空 + 去空格;数据库层 `unique=True` 兜底防并发重复。

#### password_hash
- **禁止保存明文密码**。
- 使用 Werkzeug `generate_password_hash(password)` 生成(默认 pbkdf2:sha256)。
- 校验:`check_password_hash(password_hash, password)`。
- 序列化(`to_dict`)**不返回**此字段。

#### role
- 角色枚举,Model 层定义 `VALID_ROLES = ('admin', 'contract_manager', 'employee')`。
- 注册时校验合法性,默认 `employee`。
- 写入 JWT claims,供 `role_required()` 校验。

#### created_time / updated_time
- UTC 时间存储,序列化时格式化为 `YYYY-MM-DD HH:MM:SS`。

### 2.3 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_users_username | username | UNIQUE | 唯一索引,加速登录查询 |

> 登录走 `User.query.filter_by(username=...).first()`,username 唯一索引保证查询效率与并发安全。

### 2.4 约束

| 约束 | 说明 |
|------|------|
| PRIMARY KEY | id |
| UNIQUE | username(数据库层 + 应用层双重) |
| NOT NULL | username / password_hash / role / created_time / updated_time |
| CHECK(应用层) | role ∈ ('admin', 'contract_manager', 'employee') |

### 2.5 Model 定义

文件:`backend/app/models/user.py`

```python
class User(db.Model):
    __tablename__ = 'users'
    VALID_ROLES = ('admin', 'contract_manager', 'employee')

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='employee')
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    def set_password(self, password): ...
    def check_password(self, password): ...
    def to_dict(self): ...  # 不含 password_hash
```

### 2.6 建表 DDL(MySQL 参考)

```sql
CREATE TABLE users (
    id            INT          NOT NULL AUTO_INCREMENT,
    username      VARCHAR(64)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(32)  NOT NULL DEFAULT 'employee',
    created_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 三、contracts 表(v0.4.0 新增)

### 3.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| contract_no | String(64) | NOT NULL, UNIQUE, INDEX | 合同编号(自动生成 `CT-YYYYMMDDHHMMSS-XXXXXXXX`) |
| title | String(255) | NOT NULL | 合同标题(默认取文件名去扩展名) |
| contract_type | String(64) | NOT NULL, DEFAULT '未分类' | 合同类型 |
| description | Text | nullable | 描述(可选) |
| creator_id | Integer | NOT NULL, FK → users.id, INDEX | 创建者外键 |
| status | String(32) | NOT NULL, DEFAULT 'draft' | 生命周期状态 |
| file_name | String(255) | NOT NULL | 原始文件名 |
| file_path | String(512) | NOT NULL | 服务器存储路径(UUID 文件名,**不暴露给客户端**) |
| file_size | Integer | NOT NULL, DEFAULT 0 | 文件大小(字节) |
| analysis_status | String(32) | NOT NULL, DEFAULT 'processing' | AI 分析状态 |
| analysis_result | JSON | nullable | AI 提取的字段(JSON) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 3.2 字段说明

#### contract_no
- 合同编号,全局唯一,自动生成 `CT-{YYYYMMDDHHMMSS}-{8位UUID大写}`,避免并发冲突。
- 应用层 + 数据库层双重唯一约束。

#### creator_id
- 外键关联 `users.id`,建立 **User → Contract 一对多** 关系。
- 通过 SQLAlchemy `relationship` + `backref` 实现(在 Contract 侧声明,**不修改 user.py**)。
- `lazy='dynamic'` 返回查询对象,避免一次性加载所有合同。

#### status(生命周期状态机)
- Sprint 2 仅实现:`draft`(草稿)、`reviewed`(已审核)、`archived`(已归档)。
- 预留(后续 Sprint):`uploaded`、`analyzing`、`approved`。
- 状态机转换矩阵(单向流转):

| 当前 \ 目标 | draft | reviewed | archived |
|------------|:-----:|:--------:|:--------:|
| **draft** | 禁止 | ✅允许 | 禁止 |
| **reviewed** | 禁止 | 禁止 | ✅允许 |
| **archived** | 禁止 | 禁止 | 禁止(终态) |

- 非法跳转(同状态 / 跨级 / 回退 / 终态转出)由 `Contract.is_valid_transition()` 校验,抛 `BusinessError`。
- Model 层定义:`VALID_STATUSES = ('draft','reviewed','archived')`、`STATUS_TRANSITIONS`。

#### analysis_status(AI 分析状态,独立维度)
- 值:`pending`(预留,异步用)、`processing`(分析中)、`completed`(成功)、`failed`(失败)。
- 无状态机,由 `create_contract` 流程单向推进:`processing` → `completed` / `failed`。
- AI 失败 ≠ 上传失败:合同记录必持久化,仅 `analysis_status` 标记为 `failed`。

#### analysis_result
- `db.JSON` 类型(SQLAlchemy 原生,SQLite 存为 TEXT,MySQL 可用原生 JSON 列)。
- 存储 `extract_contract_fields` 返回的字段 dict(`contract_name` / `party_a` / `party_b` / `amount` / `signing_date`)。
- 详情接口读取已有结果,**不重新调用 AI**。
- **已知限制**:Sprint 3 将迁移至独立 `contract_fields` 表(支持字段级 `confidence` 与多版本);当前 JSON 列为 Sprint 2 临时方案。

#### file_path / file_name / file_size
- `file_path`:服务器内部存储路径(`uploads/contracts/{uuid}.ext`),**不出现在 `to_dict()` 响应中**。
- `file_name`:客户端上传的原始文件名(用于展示)。
- `file_size`:文件字节数。
- 响应仅返回 `file_info: {name, size}`,不暴露内部路径。

### 3.3 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_contracts_contract_no | contract_no | UNIQUE | 唯一索引,加速编号查询 |
| idx_contracts_creator_id | creator_id | INDEX | 加速按创建者过滤(employee 权限查询) |

> 列表查询默认按 `created_time DESC` 排序;`creator_id` 索引支撑 employee 权限过滤与创建者筛选。

### 3.4 约束

| 约束 | 说明 |
|------|------|
| PRIMARY KEY | id |
| UNIQUE | contract_no(数据库层 + 应用层生成保证) |
| FOREIGN KEY | creator_id → users.id |
| NOT NULL | contract_no / title / contract_type / creator_id / status / file_name / file_path / file_size / analysis_status / created_time / updated_time |
| CHECK(应用层) | status ∈ ('draft','reviewed','archived');状态机转换合法性 |

### 3.5 Model 定义

文件:`backend/app/models/contract.py`

```python
class Contract(db.Model):
    __tablename__ = 'contracts'
    VALID_STATUSES = ('draft', 'reviewed', 'archived')
    STATUS_TRANSITIONS = {
        'draft': {'reviewed'},
        'reviewed': {'archived'},
        'archived': set(),
    }

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    contract_type = db.Column(db.String(64), nullable=False, default='未分类')
    description = db.Column(db.Text, nullable=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default='draft')
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    analysis_status = db.Column(db.String(32), nullable=False, default='processing')
    analysis_result = db.Column(db.JSON, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    creator = db.relationship('User', backref=db.backref('contracts', lazy='dynamic'))

    @classmethod
    def is_valid_transition(cls, current_status, target_status): ...
    def to_dict(self, include_analysis=True): ...  # 不含 file_path
```

### 3.6 建表 DDL(MySQL 参考)

```sql
CREATE TABLE contracts (
    id              INT          NOT NULL AUTO_INCREMENT,
    contract_no     VARCHAR(64)  NOT NULL,
    title           VARCHAR(255) NOT NULL,
    contract_type   VARCHAR(64)  NOT NULL DEFAULT '未分类',
    description     TEXT         NULL,
    creator_id      INT          NOT NULL,
    status          VARCHAR(32)  NOT NULL DEFAULT 'draft',
    file_name       VARCHAR(255) NOT NULL,
    file_path       VARCHAR(512) NOT NULL,
    file_size       INT          NOT NULL DEFAULT 0,
    analysis_status VARCHAR(32)  NOT NULL DEFAULT 'processing',
    analysis_result JSON         NULL,
    created_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_contracts_contract_no (contract_no),
    KEY idx_contracts_creator_id (creator_id),
    CONSTRAINT fk_contracts_creator FOREIGN KEY (creator_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 四、documents 表(v0.5.0 新增)

### 4.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| contract_id | Integer | NOT NULL, FK → contracts.id, INDEX | 关联合同 |
| file_name | String(255) | NOT NULL | 原始文件名 |
| file_path | String(512) | NOT NULL | 存储路径(UUID,不暴露) |
| file_size | Integer | NOT NULL, DEFAULT 0 | 文件大小(字节) |
| file_type | String(16) | NOT NULL, DEFAULT 'pdf' | pdf / image |
| page_count | Integer | NOT NULL, DEFAULT 0 | 页数(PDF) |
| text_content | Text | nullable | 提取的全文(extract/ocr 产物) |
| text_length | Integer | NOT NULL, DEFAULT 0 | 文本长度 |
| extract_method | String(32) | NOT NULL, DEFAULT 'none' | pdfplumber / deepseek_ocr / none |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 4.2 设计说明

- **解耦**:将"文件 + 提取文本"从 `contracts` 表剥离,`contracts` 只保留合同业务元信息。
- **text_content 落库**:LLM 失败重跑无需重新 OCR/提取(节省算力);支持失败重试。
- **1:1 关系**:本阶段一个合同对应一个文档(`contract_id` 不建唯一约束,预留未来多版本)。
- **to_dict()** 不返回 `file_path`(内部路径);`text_content` 默认不返回(按需 `include_text=True`)。

### 4.3 关系

- `contract_id` → `contracts.id`:Contract → Document 一对多(通过 backref)。
- Document → AnalysisTask 一对多(一个文档可被多次分析)。

---

## 五、analysis_tasks 表(v0.5.0 新增)

### 5.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| task_no | String(64) | NOT NULL, UNIQUE, INDEX | 任务编号 `AT-YYYYMMDDHHMMSS-XXXXXXXX` |
| contract_id | Integer | NOT NULL, FK → contracts.id, INDEX | 关联合同 |
| document_id | Integer | NOT NULL, FK → documents.id, INDEX | 关联文档 |
| status | String(32) | NOT NULL, DEFAULT 'pending' | pending / running / success / failed |
| current_stage | String(32) | nullable | extract / ocr / clean / chunk / llm / save |
| stages_log | JSON | nullable | 各 Stage 执行日志数组 |
| error_message | Text | nullable | 失败原因 |
| triggered_by | Integer | nullable, FK → users.id, INDEX | 触发者 |
| started_time | DateTime | nullable | 开始执行时间 |
| finished_time | DateTime | nullable | 结束时间 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 5.2 状态机(单向推进)

```
pending → running → success
                   └→ failed
```

- `pending`:已创建未执行(同步执行下仅瞬时存在)。
- `running`:Pipeline 执行中。
- `success`:全部 Stage 成功。
- `failed`:某 Stage 失败(LLM 失败 / OCR 失败 / 无文本等)。

### 5.3 stages_log 结构(JSON 数组)

```json
[
  {"stage": "extract", "status": "success", "duration_ms": 127, "error": null, "metadata": {"page_count": 1, "text_length": 57, "method": "pdfplumber"}},
  {"stage": "ocr",     "status": "skipped", "duration_ms": 0,   "error": null, "metadata": {"reason": "should_run=False"}},
  {"stage": "clean",   "status": "success", "duration_ms": 3,   "error": null, "metadata": {"original_length": 57, "cleaned_length": 55}},
  {"stage": "chunk",   "status": "success", "duration_ms": 1,   "error": null, "metadata": {"chunk_count": 1, "total_length": 55}},
  {"stage": "llm",     "status": "failed",  "duration_ms": 5,   "error": "DEEPSEEK_API_KEY 未配置,无法调用 LLM", "metadata": {}}
]
```

### 5.4 关系

- `contract_id` → `contracts.id`:Contract → AnalysisTask 一对多(支持重跑)。
- `document_id` → `documents.id`:Document → AnalysisTask 一对多。
- `triggered_by` → `users.id`:User → AnalysisTask 一对多(通过 backref)。

### 5.5 Contract.analysis_status 回写

任务完成后,`Contract.analysis_status` 按状态映射回写(保持前端兼容):

| Task.status | Contract.analysis_status |
|-------------|--------------------------|
| pending / running | processing |
| success | completed |
| failed | failed |

---

## 六、contract_fields 表(v0.5.0 新增)

### 6.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| contract_id | Integer | NOT NULL, FK → contracts.id, INDEX | 关联合同 |
| task_id | Integer | NOT NULL, FK → analysis_tasks.id, INDEX | 来源任务 |
| field_name | String(64) | NOT NULL | 字段名(8 枚举之一) |
| field_value | Text | nullable | 字段值(允许 null,表示未提取到) |
| confidence | Float | NOT NULL, DEFAULT 0.0 | 置信度 0.0–1.0 |
| source_text | Text | nullable | 字段来源文本片段(可追溯) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 时间戳 |

### 6.2 字段名枚举(8 个,与 LLM 输出契约一致)

| field_name | 中文标签 | 说明 |
|------------|----------|------|
| contract_no | 合同编号 | 如 HT-2024-001 |
| contract_name | 合同名称 | 如 软件开发合同 |
| party_a | 甲方 | 合同甲方全称 |
| party_b | 乙方 | 合同乙方全称 |
| amount | 合同金额 | 含货币单位 |
| sign_date | 签署日期 | 如 2024年1月15日 |
| payment_method | 付款方式 | 如 分期付款 |
| valid_period | 有效期 | 如 自签署之日起一年 |

### 6.3 唯一约束

```sql
UNIQUE (contract_id, field_name, task_id)  -- 同任务同字段不重复
```

### 6.4 设计说明

- **替代 Sprint 2 `analysis_result` JSON 列**:字段级 `confidence` + `source_text`,支持审计与质量评估。
- **字段级存储**:每字段一行,可独立查询 / 索引。
- **value=null**:表示"已尝试提取但未找到"(confidence=0.0);与"未分析"区分。
- **多版本支持**:`task_id` 区分不同分析任务的结果(本阶段只读最新)。

### 6.5 兼容策略(降级读取)

`get_contract_fields` 接口读取顺序:
1. 优先读最新成功任务(success)的 `contract_fields`。
2. 若无,降级读 `contracts.analysis_result`(Sprint 2 旧合同),映射为 8 字段(旧字段 `signing_date → sign_date`,新字段补 null)。
3. 都没有则返回空。

---

## 七、knowledge_documents 表(v0.6.0 新增)

### 7.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| doc_no | String(64) | NOT NULL, UNIQUE, INDEX | 文档编号(自动生成 `KD-YYYYMMDDHHMMSS-XXXXXXXX`) |
| title | String(255) | NOT NULL | 文档标题(默认取文件名去扩展名) |
| source_type | String(32) | NOT NULL, DEFAULT 'manual_upload' | 来源类型(manual_upload / contract,本阶段仅 manual_upload) |
| file_name | String(255) | NOT NULL | 原始文件名(展示用) |
| file_path | String(512) | NOT NULL | 服务器存储路径(UUID 文件名,**不暴露给客户端**) |
| file_size | Integer | NOT NULL, DEFAULT 0 | 文件大小(字节) |
| file_type | String(16) | NOT NULL, DEFAULT 'txt' | 文件类型(pdf / docx / txt) |
| page_count | Integer | NOT NULL, DEFAULT 0 | 页数(PDF;docx/txt 默认 1) |
| text_content | Text | nullable | 提取的全文(loader 产物) |
| text_length | Integer | NOT NULL, DEFAULT 0 | 文本长度 |
| chunk_count | Integer | NOT NULL, DEFAULT 0 | Chunk 数量(冗余,列表展示用,避免 COUNT JOIN) |
| embedding_status | String(32) | NOT NULL, DEFAULT 'pending' | Embedding 状态 |
| vector_indexed | Boolean | NOT NULL, DEFAULT False | 是否已写入 FAISS 索引 |
| uploader_id | Integer | nullable, FK → users.id, INDEX | 上传者外键 |
| status | String(32) | NOT NULL, DEFAULT 'active' | 文档状态(active / deleted,软删) |
| error_message | Text | nullable | 处理失败原因 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 7.2 字段说明

#### doc_no
- 知识文档编号,全局唯一,自动生成 `KD-{YYYYMMDDHHMMSS}-{8位UUID大写}`,避免并发冲突。
- 应用层 + 数据库层双重唯一约束。

#### source_type
- `manual_upload`:用户手动上传(本阶段唯一支持)。
- `contract`:预留,未来从合同文档导入知识库(Sprint 4 未实现)。

#### embedding_status(状态机,单向推进)

```
pending → processing → completed
                     └→ failed
```

- `pending`:已建记录未处理(本阶段同步执行,仅瞬时存在)。
- `processing`:正在切分 / Embedding / 入库(本阶段同步,瞬时)。
- `completed`:已写入 FAISS,可检索。
- `failed`:处理失败(模型不可用 / 文本为空等);文档与 Chunk 仍持久化,可删除后重新上传。

> 为 Sprint 8 异步化预留:未来引入 Celery 后,`processing` 将持续整个异步任务周期。

#### vector_indexed
- 布尔值,标记该文档的 Chunk 向量是否已写入 FAISS。
- 删除时据此决定是否需要从 FAISS 移除向量。
- Embedding 失败时为 `False`。

#### status(文档状态,软删)
- `active`:可用,可检索。
- `deleted`:软删(从 FAISS 移除向量,记录保留以便审计;物理文件保留)。
- 软删策略:删除知识文档时不物理删除记录,仅置 `status=deleted` 并从 FAISS 移除向量。

#### text_content
- 提取的全文(loader 产物),可能很大(Text 类型)。
- 列表场景不返回(`to_dict(include_text=False)`);详情场景按需返回。
- 落库目的:支持失败重跑 / 审计,避免重新解析。

#### chunk_count
- 冗余字段,记录该文档的 Chunk 数量。
- 列表展示用,避免 `COUNT JOIN knowledge_chunks`。

### 7.3 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_knowledge_docs_doc_no | doc_no | UNIQUE | 唯一索引,加速编号查询 |
| idx_knowledge_docs_uploader_id | uploader_id | INDEX | 加速按上传者过滤 |

### 7.4 关系

- `uploader_id` → `users.id`:User → KnowledgeDocument 一对多(通过 backref,不修改 user.py)。
- KnowledgeDocument → KnowledgeChunk 一对多(`cascade='all, delete-orphan'`)。

### 7.5 设计说明

- **独立于合同 documents 表(Sprint 3)**:职责分离 —— 合同 documents 服务于合同字段提取;知识文档服务于 RAG 检索。两表结构相似但业务域不同。
- **to_dict() 不返回 `file_path`**(内部路径);`text_content` 默认不返回。
- **禁止修改 Sprint 3 的 Document / AnalysisTask / ContractField 表**(任务书约束)。

### 7.6 建表 DDL(MySQL 参考)

```sql
CREATE TABLE knowledge_documents (
    id               INT          NOT NULL AUTO_INCREMENT,
    doc_no           VARCHAR(64)  NOT NULL,
    title            VARCHAR(255) NOT NULL,
    source_type      VARCHAR(32)  NOT NULL DEFAULT 'manual_upload',
    file_name        VARCHAR(255) NOT NULL,
    file_path        VARCHAR(512) NOT NULL,
    file_size        INT          NOT NULL DEFAULT 0,
    file_type        VARCHAR(16)  NOT NULL DEFAULT 'txt',
    page_count       INT          NOT NULL DEFAULT 0,
    text_content     TEXT         NULL,
    text_length      INT          NOT NULL DEFAULT 0,
    chunk_count      INT          NOT NULL DEFAULT 0,
    embedding_status VARCHAR(32)  NOT NULL DEFAULT 'pending',
    vector_indexed   TINYINT(1)   NOT NULL DEFAULT 0,
    uploader_id      INT          NULL,
    status           VARCHAR(32)  NOT NULL DEFAULT 'active',
    error_message    TEXT         NULL,
    created_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_knowledge_docs_doc_no (doc_no),
    KEY idx_knowledge_docs_uploader_id (uploader_id),
    CONSTRAINT fk_knowledge_docs_uploader FOREIGN KEY (uploader_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 7.7 增量迁移(v0.9.0 补充:knowledge_type 字段)

v0.9.0(Sprint 7)在 `knowledge_documents` 表新增 `knowledge_type` 字段,用于区分知识来源类型,支撑 Proposal Agent 按类型过滤检索(如仅检索企业资料 `company`)。采用增量迁移(不重建表、不丢失现有知识文档):

- **迁移脚本**:`backend/migrations/sprint7_add_knowledge_type.py`(幂等,列已存在时跳过)
- **SQL**:`ALTER TABLE knowledge_documents ADD COLUMN knowledge_type VARCHAR(32) NOT NULL DEFAULT 'general'; CREATE INDEX idx_knowledge_docs_type ON knowledge_documents(knowledge_type);`
- **回填策略**:旧知识文档记录自动回填 `knowledge_type='general'`(向后兼容,不影响 Sprint 4 RAG 检索)
- **备份**:迁移前自动复制 `instance/app.db` → `instance/app.db.bak_sprint7_knowledge_type`
- **影响范围**:仅 `knowledge_documents` 表;不涉及 Sprint 3/5/6 任何表,不修改 Sprint 4 Embedding / VectorStore / Retriever 组件

**knowledge_type 取值**:

| 取值 | 含义 | 用途 |
|------|------|------|
| `general` | 通用知识(默认) | 合同规范 / 法规(Sprint 4 原始用途) |
| `contract` | 合同知识 | 合同模板 / 历史合同条款 |
| `bid` | 招标知识 | 历史招标文件 / 招标规范 |
| `company` | 企业资料 | 公司简介 / 资质证书(Sprint 7 Proposal Agent 使用) |
| `case` | 案例 | 历史项目案例 / 业绩证明 |
| `qualification` | 资质 | 企业资质文件 / 认证证书 |

> Proposal Agent 的 `bid_knowledge_search_tool` 复用 Sprint 4 retriever,仅在上层按 `knowledge_type` 后过滤(不新增第二套 Embedding/VectorStore)。

---

## 八、knowledge_chunks 表(v0.6.0 新增)

### 8.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| document_id | Integer | NOT NULL, FK → knowledge_documents.id, INDEX | 所属知识文档 |
| chunk_index | Integer | NOT NULL | 文档内 chunk 序号(从 0 开始) |
| page_number | Integer | NOT NULL, DEFAULT 0 | 来源页码(PDF;docx/txt 为 0) |
| start_offset | Integer | NOT NULL, DEFAULT 0 | 在全文中的起始字符偏移 |
| end_offset | Integer | NOT NULL, DEFAULT 0 | 在全文中的结束字符偏移(不含) |
| token_count | Integer | NOT NULL, DEFAULT 0 | Token 估算数(中文按字符数/1.5 近似) |
| text | Text | NOT NULL | Chunk 文本内容 |
| metadata | JSON | nullable | 扩展元信息(段落序号 / overlap 标记等) |
| vector_id | Integer | nullable, INDEX | FAISS 中的向量索引 ID(删除时定位) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |

> 注:Python 属性名为 `chunk_metadata`(因 `metadata` 是 SQLAlchemy Declarative 保留属性名),通过 `db.Column('metadata', db.JSON)` 映射 DB 列名为 `metadata`,满足任务书对 `knowledge_chunks.metadata` 字段要求。

### 8.2 字段说明

#### document_id
- 外键关联 `knowledge_documents.id`,建立 **KnowledgeDocument → KnowledgeChunk 一对多** 关系。
- 通过 SQLAlchemy `relationship` + `backref` 实现(在 KnowledgeDocument 侧声明)。

#### chunk_index
- 文档内 chunk 序号,从 0 开始连续编号。
- 与 `document_id` 组合唯一(防同文档同序号重复写入)。

#### page_number
- 来源页码(PDF 为 1-based;docx/txt 为 0)。
- 由 `parser.locate_page(page_map, start_offset)` 根据起始偏移定位。

#### start_offset / end_offset
- 在全文(`knowledge_documents.text_content`)中的字符偏移区间 `[start_offset, end_offset)`。
- **含 overlap 内容**:相邻 chunk 在 offset 上有重叠区间(默认 overlap=200 字符)。
- 用于审计:可从全文精确截取 chunk 文本验证。

#### token_count
- Token 估算数:中文字符按 1 token,英文/数字按 1.5 字符 ≈ 1 token(`cjk + int(other / 1.5)`)。
- 估算值,Embedding 模型不强制要求精确 token。

#### text
- Chunk 文本内容,NOT NULL。
- 为切分产物,长度受 `chunk_size`(默认 500 字符)+ `overlap`(默认 200)约束。

#### metadata
- JSON 类型,扩展元信息(段落序号 / 是否 overlap 内容 / 章节标题等)。
- 本阶段由 `SemanticChunker` 写入(可空)。

#### vector_id
- FAISS 向量索引 ID,由 `FaissVectorStore.add()` 分配后回写。
- 删除 chunk / 文档时据此从 FAISS 索引移除对应向量(`faiss.IDSelectorBatch`)。
- 初始为 `NULL`;Embedding 失败时保持 `NULL`。

### 8.3 唯一约束

```sql
UNIQUE (document_id, chunk_index)  -- 同文档同序号不重复(name: uq_knowledge_chunk_doc_index)
```

### 8.4 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_knowledge_chunks_document_id | document_id | INDEX | 加速按文档查询 chunk |
| idx_knowledge_chunks_vector_id | vector_id | INDEX | 加速按 vector_id 查询(删除时定位) |
| uq_knowledge_chunk_doc_index | (document_id, chunk_index) | UNIQUE | 防重复写入 |

### 8.5 设计说明

- **解决 Sprint 3 Final Check 三个问题**:
  1. **Chunk 缺少 Metadata** → 本表含 `page_number` / `start_offset` / `end_offset` / `token_count` / `metadata` 全字段。
  2. **Chunk 未持久化** → 每个 chunk 落库一行,可重复检索,不丢失。
  3. **Chunk 无 Overlap** → `SemanticChunker` 切分时引入 overlap(默认 200 字符),`start_offset`/`end_offset` 记录真实位置(含 overlap 内容),相邻 chunk 在 offset 上有重叠区间。
- **与 Sprint 3 的合同 Pipeline chunk 完全独立**:合同 chunk 为内存 transient 产物(仅用于 LLM 字段提取);知识 chunk 为持久化检索单元。
- **vector_id 解耦**:FAISS 不存原始文本,溯源信息靠 `vector_id → chunk_id → knowledge_chunks.text` 链路。

### 8.6 建表 DDL(MySQL 参考)

```sql
CREATE TABLE knowledge_chunks (
    id          INT     NOT NULL AUTO_INCREMENT,
    document_id INT     NOT NULL,
    chunk_index INT     NOT NULL,
    page_number INT     NOT NULL DEFAULT 0,
    start_offset INT    NOT NULL DEFAULT 0,
    end_offset   INT    NOT NULL DEFAULT 0,
    token_count INT     NOT NULL DEFAULT 0,
    text        TEXT    NOT NULL,
    metadata    JSON    NULL,
    vector_id   INT     NULL,
    created_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_knowledge_chunks_document_id (document_id),
    KEY idx_knowledge_chunks_vector_id (vector_id),
    UNIQUE KEY uq_knowledge_chunk_doc_index (document_id, chunk_index),
    CONSTRAINT fk_knowledge_chunks_doc FOREIGN KEY (document_id) REFERENCES knowledge_documents(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 九、数据访问规范

### 9.1 调用链

```
api/auth/routes.py            → auth_service     → models/user.py
api/contract/routes.py        → contract_service → models/contract.py
                                                 → services/document_service (AI 复用)
  ↓
extensions/db.py           (SQLAlchemy session)
```

**禁止**:
- API 层直接 `User.query` / `Contract.query`(必须经 Service)
- 业务代码直接 `cursor.execute()`(必须走 ORM)
- 直接操作文件路径访问 SQLite

### 9.2 常用查询

| 场景 | 代码 |
|------|------|
| 按用户名查询 | `User.query.filter_by(username=...).first()` |
| 按 ID 查询 | `db.session.get(User, uid)` / `db.session.get(Contract, cid)` |
| 合同分页列表 | `Contract.query.filter(...).order_by(Contract.created_time.desc()).paginate(...)` |
| employee 权限过滤 | `Contract.query.filter_by(creator_id=current_user.id)` |

---

## 十、review_reports 表(v0.7.0 Sprint 5 / v0.7.1 增强)

合同 AI 风险审核报告持久化表。每次触发审核创建一条记录,记录 Agent 执行结果(风险等级 / 风险详情 / 工具调用轨迹 / Agent Trace / LLM 错误等)。

**Model**:`app/models/review_report.py` → `ReviewReport`

### 10.1 表结构

| 字段 | 类型 | 可空 | 默认 | 说明 |
|------|------|------|------|------|
| id | INT | 否 | AUTO_INCREMENT | 主键 |
| review_no | VARCHAR(64) | 否 | - | 审核编号(RV-YYYYMMDDHHMMSS-XXXXXXXX,UUID 大写),UNIQUE |
| contract_id | INT | 否 | - | 合同 ID,FK → contracts.id,INDEX |
| task_id | INT | 是 | NULL | 关联分析任务 ID,FK → analysis_tasks.id,INDEX |
| status | VARCHAR(32) | 否 | 'pending' | 状态:pending / running / success / failed |
| risk_level | VARCHAR(32) | 是 | NULL | 风险等级:high / medium / low / none(成功时填) |
| summary | TEXT | 是 | NULL | 审核总结(LLM 生成或兜底说明) |
| risks | JSON | 是 | NULL | 风险详情数组 [{type, severity, description, suggestion, evidence, rule_id, references}] |
| tool_calls_log | JSON | 是 | NULL | Agent 工具调用审计轨迹 [{tool, args, duration_ms, summary, error}] |
| agent_trace | JSON | 是 | NULL | **v0.7.1 新增** Agent 执行 Trace [{step, thought, decision, action, tool_name, tool_input, observation, start_time, end_time, duration_ms, status, error_message}] |
| trace_summary | JSON | 是 | NULL | **v0.7.1 新增** Trace 汇总统计 {steps, total_duration_ms, llm_duration_ms, tool_duration_ms, tool_stats, llm_stats, iterations, max_iterations, iteration_exceeded} |
| iterations | INT | 否 | 0 | Agent ReAct 循环迭代次数 |
| llm_error | TEXT | 是 | NULL | LLM 调用失败原因(成功时 NULL) |
| llm_error_type | VARCHAR(32) | 是 | NULL | **v0.7.1 新增** LLM 错误分类:timeout / rate_limit / server_error / network / auth / framework / json_parse / unknown |
| error_message | TEXT | 是 | NULL | Agent 执行异常信息(失败时填) |
| triggered_by | INT | 是 | NULL | 触发用户 ID,FK → users.id,INDEX |
| started_time | DATETIME | 是 | NULL | Agent 开始执行时间 |
| finished_time | DATETIME | 是 | NULL | Agent 执行完成时间 |
| created_time | DATETIME | 否 | now() | 创建时间 |
| updated_time | DATETIME | 否 | now() | 更新时间(onupdate=now()) |

> **v0.7.1 向后兼容**:`agent_trace` / `trace_summary` / `llm_error_type` 为新增字段,旧数据(v0.7.0)为 NULL,不影响已有功能。

### 10.2 索引

| 索引名 | 字段 | 类型 | 说明 |
|--------|------|------|------|
| PRIMARY | id | 主键 | - |
| ux_review_no | review_no | UNIQUE | 审核编号唯一 |
| idx_contract_id | contract_id | INDEX | 按合同查审核历史 |
| idx_task_id | task_id | INDEX | 关联分析任务 |
| idx_triggered_by | triggered_by | INDEX | 按触发用户查询 |
| idx_status | status | INDEX | 按状态过滤(可选) |
| idx_risk_level | risk_level | INDEX | 按风险等级过滤(可选) |

### 10.3 约束

- `review_no` UNIQUE:防止并发生成重复编号(UUID + 时间戳双重保障)
- `status` 枚举校验:Python 层 `VALID_STATUSES = ('pending', 'running', 'success', 'failed')`
- `risk_level` 枚举校验:Python 层 `VALID_RISK_LEVELS = ('high', 'medium', 'low', 'none')`
- 外键:
  - `contract_id` → `contracts.id`(审核必须关联合同)
  - `task_id` → `analysis_tasks.id`(可空,关联触发审核时的分析任务)
  - `triggered_by` → `users.id`(可空,记录触发用户)

### 10.4 状态流转

```
pending  → running  (Agent 开始执行)
running  → success  (Agent 正常完成,risks 已落库)
running  → failed   (Agent 异常退出,error_message 填充)
```

> 注:LLM 不可用走兜底路径时,`status = success`(报告已生成),但 `summary` 注明 LLM 不可用,`llm_error` 填充错误原因。

### 10.5 risks JSON 结构

```json
[
  {
    "type": "付款风险",
    "severity": "medium",
    "description": "合同未明确付款方式,存在付款条款模糊风险",
    "suggestion": "建议补充明确的付款方式、付款节点与付款周期",
    "evidence": "付款方式字段缺失",
    "rule_id": "R001",
    "references": [
      {
        "document_title": "企业合同管理规范.docx",
        "chunk_id": 42,
        "page_number": 3,
        "score": 0.8923,
        "document_label": "[文档1]",
        "chunk_index": 0,
        "text": "付款周期不得超过 30 天..."
      }
    ]
  }
]
```

> `references` 字段:规则风险(R001-R011)为空数组;LLM 综合风险可包含 knowledge_search_tool 检索到的引用。

### 10.6 典型查询

| 场景 | SQLAlchemy 语句 |
|------|----------------|
| 查询审核详情 | `db.session.get(ReviewReport, review_id)` |
| 合同审核历史 | `ReviewReport.query.filter_by(contract_id=cid).order_by(ReviewReport.created_time.desc()).paginate(...)` |
| 全局列表 + 过滤 | `ReviewReport.query.filter_by(risk_level=level, status=status).order_by(...)` |
| employee 权限过滤 | `ReviewReport.query.join(Contract, ReviewReport.contract_id == Contract.id).filter(Contract.creator_id == uid)` |

### 10.7 agent_trace JSON 结构(v0.7.1 新增)

```json
[
  {
    "step": 1,
    "thought": "迭代 1: 调用 LLM 决策",
    "decision": "LLM 返回决策 JSON,待解析",
    "action": "llm_call",
    "tool_name": "",
    "tool_input": {},
    "observation": {"response_length": 146, "response_preview": "..."},
    "start_time": "2026-08-06T02:09:56.508000",
    "end_time": "2026-08-06T02:09:57.803000",
    "duration_ms": 1295,
    "status": "success",
    "error_message": ""
  },
  {
    "step": 2,
    "thought": "首先调用风险规则工具获取规则化风险基线",
    "decision": "风险规则工具能提供确定性的规则风险列表",
    "action": "call_tool",
    "tool_name": "risk_rule_tool",
    "tool_input": {},
    "observation": {"count": 7, "risks": [...]},
    "start_time": "...",
    "end_time": "...",
    "duration_ms": 149,
    "status": "success",
    "error_message": ""
  }
]
```

**action 枚举**:

| 值 | 说明 |
|----|------|
| llm_call | LLM 决策调用 |
| call_tool | 调用 Tool 执行 |
| final_report | 生成最终报告 |
| system | 系统处理(JSON 重试 / 未知动作反馈) |
| iteration_exceeded | 达到迭代上限 |
| fallback | 降级 RiskRuleTool |

### 10.8 trace_summary JSON 结构(v0.7.1 新增)

```json
{
  "steps": 6,
  "total_duration_ms": 7590,
  "llm_duration_ms": 7233,
  "tool_duration_ms": 357,
  "tool_stats": {
    "risk_rule_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 151, "last_error": null},
    "knowledge_search_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 199, "last_error": null}
  },
  "llm_stats": {"call_count": 3, "total_ms": 7233, "error": null},
  "iterations": 3,
  "max_iterations": 5,
  "iteration_exceeded": false
}
```

---

## 十一、contract_templates 表(v0.8.0 Sprint 6 新增 / v0.8.1 补充 version 字段)

### 11.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| template_no | String(64) | NOT NULL, UNIQUE, INDEX | 模板编号(自动生成 `TPL-YYYYMMDDHHMMSS-XXXXXXXX`) |
| name | String(255) | NOT NULL | 模板名称(默认取文件名去扩展名,可由用户指定) |
| description | Text | nullable | 模板说明(可选) |
| contract_type | String(64) | NOT NULL, DEFAULT '未分类' | 合同类型(采购/销售/服务/未分类 等) |
| file_name | String(255) | NOT NULL | 原始文件名(客户端上传的 .docx) |
| file_path | String(512) | NOT NULL | 服务器存储路径(UUID 文件名 `uploads/templates/{uuid}.docx`,**不暴露给客户端**) |
| file_size | Integer | NOT NULL, DEFAULT 0 | 文件大小(字节) |
| variables | JSON | nullable | 解析出的变量列表(结构见 11.2) |
| variable_count | Integer | NOT NULL, DEFAULT 0 | 变量数量(冗余,便于列表展示) |
| version | String(32) | NOT NULL, DEFAULT 'v1.0' | 模板版本(v0.8.1 补充;语义化版本,用于区分同名模板的不同迭代版本) |
| status | String(32) | NOT NULL, DEFAULT 'active' | 状态(active / disabled,可反复切换) |
| creator_id | Integer | NOT NULL, FK → users.id, INDEX | 创建者外键 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 11.2 variables 字段结构(JSON 数组)

由 `docxtpl.get_undeclared_template_variables()` 解析 Word 模板中的 `{{variable}}` 占位符得出,每项结构:

```json
[
  {
    "name": "party_a",
    "label": "甲方",
    "required": true,
    "sample": "采购方公司"
  },
  {
    "name": "amount",
    "label": "金额",
    "required": true,
    "sample": "100000"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 变量名(docxtpl 占位符名,前端表单字段 key) |
| label | string | 显示名(默认取 `name`,管理员可维护) |
| required | boolean | 是否必填(默认 false) |
| sample | string | 示例值(从模板上下文推断,可能为 null) |

### 11.3 字段说明

#### template_no
- 模板编号,全局唯一,自动生成 `TPL-{YYYYMMDDHHMMSS}-{8位UUID大写}`,避免并发冲突。
- 应用层 + 数据库层双重唯一约束。

#### status(状态机,与合同不同,可双向切换)
- `active`:可使用(出现在"可生成"列表)
- `disabled`:停用(不出现在"可生成"列表,但历史生成记录仍可查)
- `active ⇄ disabled` **可反复切换**(幂等),无单向约束(与 Contract 状态机不同)。
- 删除约束:若已被用于生成(存在 `generated_contracts` 记录),**禁止硬删除**,建议停用。

#### file_path / file_name / file_size
- `file_path`:服务器内部存储路径(`uploads/templates/{uuid}.docx`),**不出现在 `to_dict()` 响应中**。
- `file_name`:客户端上传的原始文件名(用于展示)。
- `file_size`:文件字节数。
- 响应仅返回 `file_info: {name, size}`,不暴露内部路径。

#### variables / variable_count
- `db.JSON` 类型(SQLAlchemy 原生,SQLite 存为 TEXT,MySQL 可用原生 JSON 列)。
- `variable_count` 冗余字段,避免列表场景反序列化 JSON 仅为取长度。
- 上传时由 `docxtpl.get_undeclared_template_variables()` 自动解析;模板文件未修改时无需重新解析。

### 11.4 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_contract_templates_template_no | template_no | UNIQUE | 唯一索引,加速编号查询 |
| idx_contract_templates_creator_id | creator_id | INDEX | 加速按创建者过滤 |

### 11.5 约束

| 约束 | 说明 |
|------|------|
| PRIMARY KEY | id |
| UNIQUE | template_no(数据库层 + 应用层生成保证) |
| FOREIGN KEY | creator_id → users.id |
| NOT NULL | template_no / name / contract_type / file_name / file_path / file_size / variable_count / version / status / creator_id / created_time / updated_time |
| CHECK(应用层) | status ∈ ('active', 'disabled');删除前校验无 generated_contracts 关联 |

### 11.6 关系

- `creator_id` → `users.id`:User → ContractTemplate 一对多(通过 backref,不修改 user.py)。
- ContractTemplate → GeneratedContract 一对多(通过 backref,在 GeneratedContract 侧声明)。

### 11.7 Model 定义

文件:`backend/app/models/contract_template.py`

```python
class ContractTemplate(db.Model):
    __tablename__ = 'contract_templates'
    VALID_STATUSES = ('active', 'disabled')

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    template_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    contract_type = db.Column(db.String(64), nullable=False, default='未分类')
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    variables = db.Column(db.JSON, nullable=True)
    variable_count = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.String(32), nullable=False, default='v1.0')  # v0.8.1 补充
    status = db.Column(db.String(32), nullable=False, default='active')
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                           nullable=False, index=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    creator = db.relationship(
        'User',
        backref=db.backref('templates', lazy='dynamic')
    )

    def to_dict(self, include_variables=True): ...  # 不含 file_path
```

### 11.8 建表 DDL(MySQL 参考)

```sql
CREATE TABLE contract_templates (
    id              INT          NOT NULL AUTO_INCREMENT,
    template_no     VARCHAR(64)  NOT NULL,
    name            VARCHAR(255) NOT NULL,
    description     TEXT         NULL,
    contract_type   VARCHAR(64)  NOT NULL DEFAULT '未分类',
    file_name       VARCHAR(255) NOT NULL,
    file_path       VARCHAR(512) NOT NULL,
    file_size       INT          NOT NULL DEFAULT 0,
    variables       JSON         NULL,
    variable_count  INT          NOT NULL DEFAULT 0,
    version         VARCHAR(32)  NOT NULL DEFAULT 'v1.0',  -- v0.8.1 补充:模板版本
    status          VARCHAR(32)  NOT NULL DEFAULT 'active',
    creator_id      INT          NOT NULL,
    created_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_contract_templates_template_no (template_no),
    KEY idx_contract_templates_creator_id (creator_id),
    CONSTRAINT fk_contract_templates_creator FOREIGN KEY (creator_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 11.9 增量迁移(v0.8.1 补充:version 字段)

v0.8.1 在 `contract_templates` 表新增 `version` 字段,采用增量迁移(不重建表、不丢失现有模板数据):

- **迁移脚本**:`backend/migrations/sprint6_add_version.py`(幂等,列已存在时跳过)
- **SQL**:`ALTER TABLE contract_templates ADD COLUMN version VARCHAR(32) NOT NULL DEFAULT 'v1.0';`
- **回填策略**:旧模板记录自动回填 `version='v1.0'`
- **备份**:迁移前自动复制 `instance/app.db` → `instance/app.db.bak_sprint6_version`
- **影响范围**:仅 `contract_templates` 表;不涉及 Sprint 3/4/5 任何表

---

## 十二、generated_contracts 表(v0.8.0 Sprint 6 新增)

### 12.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| generation_no | String(64) | NOT NULL, UNIQUE, INDEX | 生成编号(自动生成 `GC-YYYYMMDDHHMMSS-XXXXXXXX`) |
| template_id | Integer | NOT NULL, FK → contract_templates.id, INDEX | 使用的模板 |
| contract_id | Integer | nullable, FK → contracts.id, INDEX | 生成的合同记录(生成成功后填,null=失败/预览) |
| status | String(32) | NOT NULL, DEFAULT 'pending' | 任务状态(pending / running / success / failed) |
| input_variables | JSON | nullable | 用户填写的变量键值对 |
| generated_clauses | JSON | nullable | AI 补充条款(结构见 12.2) |
| rag_references | JSON | nullable | RAG 命中规范(复用 Sprint 4 references 结构) |
| validation_results | JSON | nullable | 规则校验结果({passed, issues}) |
| file_path | String(512) | nullable | 生成 .docx 路径(失败/预览为 null) |
| file_name | String(255) | nullable | 生成 .docx 文件名 |
| file_size | Integer | nullable | 文件大小(字节) |
| agent_trace | JSON | nullable | Agent 执行 Trace(复用 Sprint 5 结构,12 字段/步) |
| trace_summary | JSON | nullable | Trace 汇总(steps / durations / tool_stats / llm_stats) |
| iterations | Integer | NOT NULL, DEFAULT 0 | Agent 迭代次数 |
| llm_error | Text | nullable | LLM 失败原因(成功为 null) |
| llm_error_type | String(32) | nullable | LLM 错误分类(复用 Sprint 5 枚举) |
| error_message | Text | nullable | 整体失败原因(成功为 null) |
| triggered_by | Integer | nullable, FK → users.id, INDEX | 触发者外键 |
| started_time | DateTime | nullable | 开始执行时间 |
| finished_time | DateTime | nullable | 结束时间 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 12.2 generated_clauses 字段结构(JSON 数组)

由 `clause_generation_tool` 调 DeepSeek 生成,每项结构:

```json
[
  {
    "name": "付款条款",
    "content": "甲方应在收到乙方开具的合规发票后 30 日内,通过银行转账方式支付合同款项...",
    "source": "clause_generation_tool",
    "references": [
      {
        "document_title": "采购合同规范",
        "chunk_id": 5,
        "page_number": 2,
        "score": 0.89
      }
    ]
  },
  {
    "name": "违约责任条款",
    "content": "任何一方未履行本合同义务,应承担违约责任...",
    "source": "clause_generation_tool",
    "references": []
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 条款名称(付款/违约/保密/知识产权/售后 等) |
| content | string | 条款正文(LLM 生成,基于 RAG 检索的企业规范) |
| source | string | 来源工具(`clause_generation_tool`) |
| references | array | 命中的 RAG 引用(复用 Sprint 4 references 结构) |

### 12.3 状态机(单向推进,与 ReviewReport 一致)

```
pending → running → success
                   └→ failed
```

- `pending`:已创建未执行(同步执行下仅瞬时存在)。
- `running`:Agent 执行中。
- `success`:Agent 完成 + Word 渲染完成 + 合同创建成功(预览场景:Agent 完成,无 Word / 无合同)。
- `failed`:Word 渲染失败 / 建合同失败 / 其他异常。

> **容错说明**:Agent 失败(LLM 不可用)**不**标记为 `failed`,而是走兜底(仅 `contract_rule_tool`,无 AI 条款)仍渲染 Word + 建合同,记录标记 `success`,`llm_error` 字段记录原因。仅 Word 渲染或建合同失败才标记 `failed`。

### 12.4 agent_trace 字段结构(JSON 数组,复用 Sprint 5)

每步 12 字段:

```json
[
  {
    "step": 1,
    "thought": "需要先查询模板变量,确认必填项是否齐全",
    "decision": "调用 template_tool 查询变量清单",
    "action": "call_tool",
    "tool_name": "template_tool",
    "tool_input": {"template_id": 1},
    "observation": {"variable_count": 4, "required": ["party_a", "party_b", "amount"]},
    "start_time": "2026-08-06 19:10:01",
    "end_time": "2026-08-06 19:10:01",
    "duration_ms": 12,
    "status": "success",
    "error_message": null
  }
]
```

> `action` 取值:`call_tool` / `final_report`;`status` 取值:`success` / `failed` / `skipped`。

### 12.5 trace_summary 字段结构(JSON)

```json
{
  "steps": 4,
  "total_duration_ms": 92000,
  "llm_duration_ms": 78000,
  "tool_duration_ms": 14000,
  "tool_stats": {
    "template_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 12, "last_error": null},
    "knowledge_search_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 199, "last_error": null},
    "clause_generation_tool": {"call_count": 2, "success_count": 2, "failed_count": 0, "total_ms": 76000, "last_error": null},
    "contract_rule_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 35, "last_error": null}
  },
  "llm_stats": {"call_count": 4, "total_ms": 78000, "error": null},
  "iterations": 4,
  "max_iterations": 5,
  "iteration_exceeded": false
}
```

### 12.6 索引

| 索引 | 字段 | 类型 | 说明 |
|------|------|------|------|
| idx_generated_contracts_generation_no | generation_no | UNIQUE | 唯一索引,加速编号查询 |
| idx_generated_contracts_template_id | template_id | INDEX | 加速按模板过滤(生成历史) |
| idx_generated_contracts_contract_id | contract_id | INDEX | 加速按合同反查生成来源 |
| idx_generated_contracts_triggered_by | triggered_by | INDEX | 加速按触发者过滤(employee 权限查询) |

### 12.7 约束

| 约束 | 说明 |
|------|------|
| PRIMARY KEY | id |
| UNIQUE | generation_no(数据库层 + 应用层生成保证) |
| FOREIGN KEY | template_id → contract_templates.id(必填) |
| FOREIGN KEY | contract_id → contracts.id(可空,生成成功后回填) |
| FOREIGN KEY | triggered_by → users.id(可空) |
| NOT NULL | generation_no / template_id / status / iterations / created_time / updated_time |
| CHECK(应用层) | status ∈ ('pending', 'running', 'success', 'failed');状态机单向推进 |

### 12.8 关系

- `template_id` → `contract_templates.id`:ContractTemplate → GeneratedContract 一对多(通过 backref,在 GeneratedContract 侧声明)。
- `contract_id` → `contracts.id`:Contract → GeneratedContract 一对多(通过 backref,不修改 contract.py)。一个合同可由多次生成(预留重试场景)。
- `triggered_by` → `users.id`:User → GeneratedContract 一对多(通过 backref,不修改 user.py)。

### 12.9 设计说明

- **任务化**:每次生成独立可追踪,支持重试(创建新 GeneratedContract,不复用旧记录)。
- **同步执行**:Sprint 6 不引入 Celery / Redis,Agent 在 HTTP 请求内同步完成。
- **预览 vs 正式**:预览场景 `contract_id=null` / `file_path=null`,但 `generated_clauses` / `agent_trace` 完整落库(可在生成记录列表查到,但不可下载)。
- **集成闭环**:生成成功后,`contract_service.create_contract_from_generation()` 创建 Contract(`status=draft`, `analysis_status=pending`),回填 `generated_contracts.contract_id`,形成"生成→解析→审核"闭环。
- **不修改** Sprint 3 的 Document / AnalysisTask / ContractField 表;不修改 Sprint 4 的 knowledge_documents / knowledge_chunks 表;不修改 Sprint 5 的 review_reports 表。

### 12.10 Model 定义

文件:`backend/app/models/generated_contract.py`

```python
class GeneratedContract(db.Model):
    __tablename__ = 'generated_contracts'
    VALID_STATUSES = ('pending', 'running', 'success', 'failed')

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    generation_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('contract_templates.id'),
                            nullable=False, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id'),
                            nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='pending')
    input_variables = db.Column(db.JSON, nullable=True)
    generated_clauses = db.Column(db.JSON, nullable=True)
    rag_references = db.Column(db.JSON, nullable=True)
    validation_results = db.Column(db.JSON, nullable=True)
    file_path = db.Column(db.String(512), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    agent_trace = db.Column(db.JSON, nullable=True)
    trace_summary = db.Column(db.JSON, nullable=True)
    iterations = db.Column(db.Integer, nullable=False, default=0)
    llm_error = db.Column(db.Text, nullable=True)
    llm_error_type = db.Column(db.String(32), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    triggered_by = db.Column(db.Integer, db.ForeignKey('users.id'),
                             nullable=True, index=True)
    started_time = db.Column(db.DateTime, nullable=True)
    finished_time = db.Column(db.DateTime, nullable=True)
    created_time = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow, nullable=False)

    template = db.relationship(
        'ContractTemplate',
        backref=db.backref('generations', lazy='dynamic')
    )
    contract = db.relationship(
        'Contract',
        backref=db.backref('generations', lazy='dynamic')
    )
    trigger_user = db.relationship(
        'User',
        backref=db.backref('triggered_generations', lazy='dynamic')
    )

    def to_dict(self, include_clauses=True, include_trace=True,
                include_contract=False, include_template=True): ...  # 不含 file_path
```

### 12.11 建表 DDL(MySQL 参考)

```sql
CREATE TABLE generated_contracts (
    id                  INT          NOT NULL AUTO_INCREMENT,
    generation_no       VARCHAR(64)  NOT NULL,
    template_id         INT          NOT NULL,
    contract_id         INT          NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'pending',
    input_variables     JSON         NULL,
    generated_clauses   JSON         NULL,
    rag_references      JSON         NULL,
    validation_results  JSON         NULL,
    file_path           VARCHAR(512) NULL,
    file_name           VARCHAR(255) NULL,
    file_size           INT          NULL,
    agent_trace         JSON         NULL,
    trace_summary       JSON         NULL,
    iterations          INT          NOT NULL DEFAULT 0,
    llm_error           TEXT         NULL,
    llm_error_type      VARCHAR(32)  NULL,
    error_message       TEXT         NULL,
    triggered_by        INT          NULL,
    started_time        DATETIME     NULL,
    finished_time       DATETIME     NULL,
    created_time        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_generated_contracts_generation_no (generation_no),
    KEY idx_generated_contracts_template_id (template_id),
    KEY idx_generated_contracts_contract_id (contract_id),
    KEY idx_generated_contracts_triggered_by (triggered_by),
    CONSTRAINT fk_generated_contracts_template FOREIGN KEY (template_id) REFERENCES contract_templates(id),
    CONSTRAINT fk_generated_contracts_contract FOREIGN KEY (contract_id) REFERENCES contracts(id),
    CONSTRAINT fk_generated_contracts_triggered_by FOREIGN KEY (triggered_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 十三、bid_documents 表(v0.9.0 Sprint 7 新增)

招标文档表(招标文件 + 提取文本,独立于合同 `documents`,保持 Sprint 2 合同表纯净)。

### 13.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| bid_no | String(64) | NOT NULL, UNIQUE, INDEX | 招标编号(自动生成 `BD-YYYYMMDDHHMMSS-XXXXXXXX`) |
| title | String(255) | NOT NULL | 招标标题(默认取文件名去扩展名) |
| file_name | String(255) | NOT NULL | 原始文件名(展示用) |
| file_path | String(512) | NOT NULL | 服务器存储路径(UUID 文件名,**不暴露给客户端**) |
| file_size | Integer | NOT NULL, DEFAULT 0 | 文件大小(字节) |
| file_type | String(16) | NOT NULL, DEFAULT 'pdf' | 文件类型(pdf / image) |
| page_count | Integer | NOT NULL, DEFAULT 0 | 页数(PDF;图片默认 1) |
| text_content | Text | nullable | 提取的全文(extract / ocr 产物,详情按需返回) |
| text_length | Integer | NOT NULL, DEFAULT 0 | 文本长度 |
| parse_status | String(32) | NOT NULL, DEFAULT 'pending' | 需求解析状态 |
| extract_method | String(32) | NOT NULL, DEFAULT 'none' | 文本提取方法(pdfplumber / deepseek_ocr / none) |
| error_message | Text | nullable | 解析失败原因 |
| uploader_id | Integer | NOT NULL, FK → users.id, INDEX | 上传者外键 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 13.2 parse_status 状态机(单向推进,与 AnalysisTask 一致)

```
pending → processing → success
                    └→ failed
```

- `pending`:已建记录未解析(本阶段同步执行,瞬时)
- `processing`:正在解析(Bid Pipeline 同步执行,瞬时)
- `success`:解析完成,已生成 `BidRequirement`
- `failed`:解析失败(LLM 不可用 / 文本为空等),可调用 `/parse` 重试

### 13.3 关系

- `User` → `BidDocument` 一对多(通过 backref,不修改 `user.py`)
- `BidDocument` → `BidRequirement` 一对一(`uselist=False`,重新解析时 UPDATE 原行,cascade delete-orphan)
- `BidDocument` → `GeneratedProposal` 一对多(一个招标文件可多次生成投标方案)

### 13.4 设计说明

- **独立表,不挂 `contracts`**:招标 ≠ 合同,保持 Sprint 2 合同表纯净
- `text_content` 落库后,LLM 失败重跑无需重新 OCR/提取(节省算力)
- `to_dict()` 不返回 `file_path`(内部路径);`text_content` 默认不返回(按需 `include_text=True`)
- **删除守卫**:有关联 `GeneratedProposal` 时拒绝删除(返回 400 提示先删除生成记录)

### 13.5 建表 DDL(MySQL 参考)

```sql
CREATE TABLE bid_documents (
    id              INT          NOT NULL AUTO_INCREMENT,
    bid_no          VARCHAR(64)  NOT NULL,
    title           VARCHAR(255) NOT NULL,
    file_name       VARCHAR(255) NOT NULL,
    file_path       VARCHAR(512) NOT NULL,
    file_size       INT          NOT NULL DEFAULT 0,
    file_type       VARCHAR(16)  NOT NULL DEFAULT 'pdf',
    page_count      INT          NOT NULL DEFAULT 0,
    text_content    TEXT         NULL,
    text_length     INT          NOT NULL DEFAULT 0,
    parse_status    VARCHAR(32)  NOT NULL DEFAULT 'pending',
    extract_method  VARCHAR(32)  NOT NULL DEFAULT 'none',
    error_message   TEXT         NULL,
    uploader_id     INT          NOT NULL,
    created_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_bid_docs_bid_no (bid_no),
    KEY idx_bid_docs_uploader_id (uploader_id),
    KEY idx_bid_docs_parse_status (parse_status),
    CONSTRAINT fk_bid_docs_uploader FOREIGN KEY (uploader_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 十四、bid_requirements 表(v0.9.0 Sprint 7 新增 / v0.9.1 Sprint 7.1 增强)

招标需求表(15 字段 Requirement JSON,1:1 关联 `BidDocument`)。

### 14.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| requirement_no | String(64) | NOT NULL, UNIQUE, INDEX | 需求编号(自动生成 `BR-YYYYMMDDHHMMSS-XXXXXXXX`) |
| bid_document_id | Integer | NOT NULL, FK → bid_documents.id, UNIQUE, INDEX | 招标文件外键(1:1) |
| version | String(32) | NOT NULL, DEFAULT 'v1.0', INDEX | 需求版本(v0.9.1 新增,后续版本 Diff 预留) |
| status | String(32) | NOT NULL, DEFAULT 'draft', INDEX | **v0.9.1 语义升级**:需求审核状态 + 解析状态<br/>合法值:draft / reviewing / approved / pending / failed<br/>- draft:解析完成,等待人工提交审核<br/>- reviewing:人工审核中<br/>- approved:审核通过,Bid Agent 只读此状态<br/>- pending:AI 解析中(旧语义保留)<br/>- failed:解析失败(旧语义保留) |
| requirement_data | JSON | nullable | 15 字段 Requirement JSON(见 14.2) |
| field_sources | JSON | nullable | **v0.9.1 新增**:字段来源追踪,见 14.3 节 |
| project_name | String(255) | nullable | 项目名称(冗余,列表展示用) |
| budget | String(64) | nullable | 预算金额(冗余,列表展示用) |
| deadline | String(64) | nullable | 投标截止时间(冗余,列表展示用) |
| field_count | Integer | NOT NULL, DEFAULT 0 | 已提取字段数(15 − missing_count) |
| missing_count | Integer | NOT NULL, DEFAULT 15 | null / 空数组字段数 |
| confidence | Float | nullable | LLM 自评置信度均值(0–1) |
| error_message | Text | nullable | 解析失败原因 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 14.2 requirement_data 15 字段结构(JSON)

由 `requirement_extractor` 调 DeepSeek 生成:

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| project_name | string | ✓ | 项目名称 |
| tender_org | string | ✓ | 招标单位 |
| project_location | string | | 项目地点 |
| budget | string | ✓ | 预算金额 |
| deadline | string(ISO) | ✓ | 投标截止时间 |
| duration | string | | 工期 / 服务期 |
| delivery_requirements | string | | 供货范围 / 交货要求 |
| technical_requirements | string[] | ✓ | 技术要求清单 |
| qualification_requirements | string[] | ✓ | 资格要求清单 |
| scoring_criteria | string[] | | 评分标准 |
| bid_opening_time | string(ISO) | | 开标时间 |
| bid_validity | string | | 投标有效期 |
| payment_terms | string | | 付款条件 |
| contact | string | | 联系人 / 电话 |
| other | string | | 其他补充说明 |

### 14.3 field_sources 字段来源 JSON 结构(v0.9.1 新增)

key = requirement_data 字段名,value = 来源对象:

```json
{
  "project_name": {
    "page_number": 3,
    "chunk_id": "bid_12_chunk_07",
    "confidence": 0.97,
    "source_text": "第二章  项目名称:某市智慧政务云平台采购"
  }
}
```

字段说明:
- `page_number`:Integer,PDF 页码
- `chunk_id`:String,Chunker 生成的 chunk 编号
- `confidence`:Float(0–1),该字段提取置信度
- `source_text`:String,原始片段(便于前端点击"查看原文")

### 14.4 设计说明(含 v0.9.1 升级)

- **1:1 关系**:一个招标文件对应一个最新需求(历史不保留,与 `AnalysisTask` 不同)
- **冗余字段**(`project_name` / `budget` / `deadline`):列表展示用,避免每行解析 JSON
- **重新解析 UPSERT**:`uselist=False` + UPDATE 原行,非 append-only;重解析时 `version` 自动递增(vX.Y → vX.(Y+1)),status 回落到 draft
- `confidence`:LLM 自评各字段置信度均值,供前端展示与 Agent 决策参考
- **v0.9.1 status 语义升级**:与审核流合并,Bid Agent 仅读取 `approved` 数据(常量 `BidRequirement.AGENT_READABLE_STATUSES = ('approved',)`)
- `field_sources`:可选,向后兼容,旧数据为 NULL 时前端隐藏"查看来源"按钮
- **不修改** Sprint 3 的 `ContractField` 表(合同字段)
- **v0.9.1 迁移**:`migrations/sprint7_1_bid_requirements_enhancement.py`(ADD COLUMN + 回填 status)

### 14.5 建表 DDL(v0.9.1 最新,MySQL 参考)

```sql
CREATE TABLE bid_requirements (
    id               INT          NOT NULL AUTO_INCREMENT,
    requirement_no   VARCHAR(64)  NOT NULL,
    bid_document_id  INT          NOT NULL,
    version          VARCHAR(32)  NOT NULL DEFAULT 'v1.0'  COMMENT 'v0.9.1 版本号',
    status           VARCHAR(32)  NOT NULL DEFAULT 'draft' COMMENT 'v0.9.1 审核状态:draft/reviewing/approved/pending/failed',
    requirement_data JSON         NULL,
    field_sources    JSON         NULL                    COMMENT 'v0.9.1 字段来源追踪',
    project_name     VARCHAR(255) NULL,
    budget           VARCHAR(64)  NULL,
    deadline         VARCHAR(64)  NULL,
    field_count      INT          NOT NULL DEFAULT 0,
    missing_count    INT          NOT NULL DEFAULT 15,
    confidence       FLOAT        NULL,
    error_message    TEXT         NULL,
    created_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_bid_req_no (requirement_no),
    UNIQUE KEY idx_bid_req_bid_doc (bid_document_id),
    KEY idx_bid_req_status (status),
    KEY idx_bid_req_version (version),
    CONSTRAINT fk_bid_req_bid_doc FOREIGN KEY (bid_document_id)
        REFERENCES bid_documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招标需求表(v0.9.1)';
```

---

## 十五、generated_proposals 表(v0.9.0 Sprint 7 新增)

投标生成记录表(Proposal Agent 执行实例,镜像 Sprint 6 `generated_contracts` 结构)。

### 15.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| proposal_no | String(64) | NOT NULL, UNIQUE, INDEX | 生成编号(自动生成 `PR-YYYYMMDDHHMMSS-XXXXXXXX`) |
| bid_document_id | Integer | NOT NULL, FK → bid_documents.id, INDEX | 关联的招标文件 |
| status | String(32) | NOT NULL, DEFAULT 'pending' | 任务状态 |
| input_data | JSON | nullable | 输入参数(bid_id / company_profile_overrides / options) |
| generated_sections | JSON | nullable | AI 生成章节(冗余,与 `proposal_sections` 表互为镜像) |
| rag_references | JSON | nullable | RAG 命中规范(复用 Sprint 4 references 结构) |
| validation_results | JSON | nullable | 规则校验结果({passed, issues}) |
| file_path | String(512) | nullable | 生成 .docx 路径(失败为 null) |
| file_name | String(255) | nullable | 生成 .docx 文件名 |
| file_size | Integer | nullable | 文件大小(字节) |
| agent_trace | JSON | nullable | Agent 执行 Trace(复用 Sprint 5 结构,12 字段/步) |
| trace_summary | JSON | nullable | Trace 汇总(steps / durations / tool_stats / llm_stats) |
| iterations | Integer | NOT NULL, DEFAULT 0 | Agent 迭代次数 |
| llm_error | Text | nullable | LLM 失败原因(成功为 null) |
| llm_error_type | String(32) | nullable | LLM 错误分类(复用 Sprint 5 枚举) |
| error_message | Text | nullable | 整体失败原因(成功为 null) |
| triggered_by | Integer | nullable, FK → users.id, INDEX | 触发者外键 |
| started_time | DateTime | nullable | 开始执行时间 |
| finished_time | DateTime | nullable | 结束时间 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

### 15.2 status 状态机(单向推进,与 generated_contracts 一致)

```
pending → running → success
                   └→ failed
```

### 15.3 关系

- `BidDocument` → `GeneratedProposal` 一对多(通过 backref,不修改 `bid_document.py`)
- `User` → `GeneratedProposal` 一对多(通过 backref,不修改 `user.py`)
- `GeneratedProposal` → `ProposalSection` 一对多(cascade='all, delete-orphan')

### 15.4 设计说明

- **镜像 `generated_contracts` 表结构**(1:1 对齐),便于前端复用 `GenerationDetail` Timeline
- `generated_sections` JSON 与 `proposal_sections` 表互为镜像:JSON 供快速预览,表供独立查询/排序/分页
- **不修改** Sprint 6 的 `generated_contracts` 表

### 15.5 建表 DDL(MySQL 参考)

```sql
CREATE TABLE generated_proposals (
    id                 INT          NOT NULL AUTO_INCREMENT,
    proposal_no        VARCHAR(64)  NOT NULL,
    bid_document_id    INT          NOT NULL,
    status             VARCHAR(32)  NOT NULL DEFAULT 'pending',
    input_data         JSON         NULL,
    generated_sections JSON         NULL,
    rag_references     JSON         NULL,
    validation_results JSON         NULL,
    file_path          VARCHAR(512) NULL,
    file_name          VARCHAR(255) NULL,
    file_size          INT          NULL,
    agent_trace        JSON         NULL,
    trace_summary      JSON         NULL,
    iterations         INT          NOT NULL DEFAULT 0,
    llm_error          TEXT         NULL,
    llm_error_type     VARCHAR(32)  NULL,
    error_message      TEXT         NULL,
    triggered_by       INT          NULL,
    started_time       DATETIME     NULL,
    finished_time      DATETIME     NULL,
    created_time       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_proposals_no (proposal_no),
    KEY idx_proposals_bid_doc (bid_document_id),
    KEY idx_proposals_status (status),
    KEY idx_proposals_triggered_by (triggered_by),
    CONSTRAINT fk_proposals_bid_doc FOREIGN KEY (bid_document_id) REFERENCES bid_documents(id),
    CONSTRAINT fk_proposals_triggered_by FOREIGN KEY (triggered_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 十六、proposal_sections 表(v0.9.0 Sprint 7 新增 / v0.9.1 Sprint 7.1 增强)

投标章节表(投标文件的章节级内容,1:N 关联 `GeneratedProposal`)。

### 16.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| proposal_id | Integer | NOT NULL, FK → generated_proposals.id, INDEX | 生成记录外键 |
| section_type | String(32) | NOT NULL | 章节类型(technical / commercial / responsive / qualification / summary) |
| section_name | String(255) | NOT NULL | 章节名称(如"技术方案"、"商务文件") |
| content | Text | nullable | 章节内容(Markdown / 纯文本) |
| source | String(32) | NOT NULL, DEFAULT 'ai' | 内容来源(ai / template / rule) |
| references | JSON | nullable | **v0.9.1 统一** RAG / 需求引用(4 字段格式,对齐 Sprint 5 Contract Review) |
| sort_order | Integer | NOT NULL, DEFAULT 0 | 排序顺序(technical=1 ... summary=5) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间(章节为生成产物,无 updated_time) |

### 16.2 section_type 枚举

| 取值 | 含义 | 必填 | sort_order |
|------|------|:----:|:----------:|
| technical | 技术方案 | ✓ | 1 |
| commercial | 商务文件 | ✓ | 2 |
| responsive | 响应文件 | ✓ | 3 |
| qualification | 资质文件 | ✓ | 4 |
| summary | 投标摘要 | | 5 |

### 16.3 source 枚举(内容来源)

- `ai`:AI 生成(`proposal_section_tool` 调 LLM)
- `template`:模板预填(从模板复制)
- `rule`:规则兜底(LLM 失败时生成骨架)

### 16.4 references JSON (v0.9.1 统一)

每条引用 4 字段,与 Sprint 5 `review_reports.references` 完全一致:

```json
[
  {"document_id": 41, "chunk_id": "kc_102", "page_number": 7, "similarity_score": 0.89},
  {"document_id": 2,  "chunk_id": "kc_3",   "page_number": 2, "similarity_score": 0.78}
]
```

字段说明:
- `document_id`:知识文档/需求 document id
- `chunk_id`:向量库 chunk id
- `page_number`:原文页码
- `similarity_score`:RAG 相似度(0–1)

> v0.9.1 统一前,Sprint 4 references 曾含 `score`/`document_title`/`text`;当前版本保留 4 项核心字段,对齐 Bid / Contract 双模块。

### 16.5 设计说明(含 v0.9.1 升级)

- **拆表而非 JSON**:章节需独立查询 / 排序 / 分页(相比 `generated_contracts.generated_clauses` JSON)
- **v0.9.1 `references` 格式统一**:Bid References ↔ Contract Review 共享格式,后续跨模块溯源接口零改造
- `sort_order` 固定顺序,便于前端按顺序渲染
- **不修改** Sprint 6 的 `generated_contracts` 表
- Bid 生成时,`trace_summary`(在 `generated_proposals.agent_trace` JSON 内)同样对齐 Sprint 5 的 10 项可观测指标(见 DDL 15.2 节)

### 16.6 建表 DDL(v0.9.1 最新,MySQL 参考)

```sql
CREATE TABLE proposal_sections (
    id           INT          NOT NULL AUTO_INCREMENT,
    proposal_id  INT          NOT NULL,
    section_type VARCHAR(32)  NOT NULL,
    section_name VARCHAR(255) NOT NULL,
    content      TEXT         NULL,
    source       VARCHAR(32)  NOT NULL DEFAULT 'ai',
    references   JSON         NULL,
    sort_order   INT          NOT NULL DEFAULT 0,
    created_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_proposal_sections_proposal (proposal_id),
    KEY idx_proposal_sections_type (section_type),
    CONSTRAINT fk_proposal_sections_proposal FOREIGN KEY (proposal_id) REFERENCES generated_proposals(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> **注意**:`references` 在 MySQL 中为保留字,建表时需用反引号包裹(`` `references` ``);SQLAlchemy ORM 层已正确处理,业务代码无影响。

---

## 十七、后续表规划(Sprint 8+)

| 版本 | 表 | 说明 | 状态 |
|------|-----|------|------|
| v0.3.0 (Sprint 1) | users | 用户表 | ✅ 已落地 |
| v0.4.0 (Sprint 2) | contracts | 合同主表 | ✅ 已落地 |
| v0.5.0 (Sprint 3) | documents / analysis_tasks / contract_fields | 文档元信息 / 分析任务 / 结构化字段 | ✅ 已落地 |
| v0.6.0 (Sprint 4) | knowledge_documents / knowledge_chunks | 知识文档 / 知识 Chunk(持久化 + metadata + overlap) | ✅ 已落地 |
| v0.7.0 (Sprint 5) | review_reports | 合同审核报告(Agent 结果持久化) | ✅ 已落地 |
| v0.8.0 (Sprint 6) | contract_templates / generated_contracts | 合同模板 / 生成记录(Generation Agent 结果持久化) | ✅ 已落地 |
| v0.9.0 (Sprint 7) | bid_documents / bid_requirements / generated_proposals / proposal_sections | 招标文件 / 招标需求 / 投标生成记录 / 投标章节 | ✅ 已落地 |
| v0.9.1 (Sprint 7.1) | bid_requirements(新增 version / field_sources,status 语义升级) + proposal_sections(统一 references 格式) | Bid 企业级增强:版本 / 审核 / 溯源 / 可观测 | ✅ 已落地 |
| v1.0+ (Sprint 8) | ai_request_logs / operation_logs / prompt_templates / evaluation_reports | 企业级增强:AI 调用日志 / 操作审计 / Prompt 版本管理 / AI 评估 | ✅ 已落地 |

> 当前已落地 18 张表:`users` / `contracts` / `documents` / `analysis_tasks` / `contract_fields` / `knowledge_documents` / `knowledge_chunks` / `review_reports` / `contract_templates` / `generated_contracts` / `bid_documents` / `bid_requirements` / `generated_proposals` / `proposal_sections` / `ai_request_logs` / `operation_logs` / `prompt_templates` / `evaluation_reports`。新增表时本文档同步更新。

---

## 十八、ai_request_logs 表(v1.0.0 Sprint 8 新增)

AI 调用可观测日志。每次 Agent.run / RAG 调用结束后,通过 `ai_log_service.log_agent_run / log_rag_call` 异步写入,**写入失败不回滚业务事务**。

### 18.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| user_id | Integer | INDEX | 发起用户(可为 NULL=匿名/未登录) |
| username | String(64) | | 用户名快照(即使 user 被删除也能保留记录) |
| agent_type | String(32) | NOT NULL, INDEX | contract_review / generation / bid_proposal / rag / contract_extract / bid_requirement |
| model | String(64) | | 实际调用模型(deepseek-chat / deepseek-reasoner 等) |
| prompt_version | String(128) | | Prompt 版本(格式:`db:<name>:<version>` 或 `file:<path>`) |
| input_tokens | Integer | | 累计输入 Token |
| output_tokens | Integer | | 累计输出 Token |
| total_tokens | Integer | INDEX | 累计总 Token(= input+output) |
| latency_ms | Integer | | 端到端耗时(毫秒) |
| status | String(16) | NOT NULL, INDEX | success / failed |
| error_message | Text | | 失败时异常摘要(不包含堆栈,避免敏感) |
| trace_summary | JSON | | 与 Sprint 5/7 `trace_summary` 相同结构(10 项可观测指标),便于回溯单步 Tool 耗时/成功率 |
| related_id | Integer | INDEX | 关联业务 ID(review_report_id / generation_id / proposal_id / document_id) |
| related_type | String(32) | INDEX | review_report / generation / proposal / document / rag |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |

### 18.2 设计要点

1. **写入绝不阻断业务**:`ai_log_service.log_agent_run()` 全部 `try ... except: logger.warning;pass` 包裹,内部 DB session 使用独立临时 commit 或子事务,异常不 raise。
2. **Token 累计使用 contextvars**:`ai/agent/llm_client.py` 维护 per-run ContextVar(`run_input_tokens`/`run_output_tokens`/`run_call_count`),每次 Agent.run 前后 reset/collect,避免跨请求串 token。
3. **related_id + related_type 通用关联**:一张表覆盖 Sprint 5/6/7 三种 Agent + Sprint 4 RAG + Sprint 3 Pipeline。
4. **查询接口仅 admin**:`GET /api/v1/logs/ai` 与 `GET /api/v1/logs/ai/{id}`。

---

## 十九、operation_logs 表(v1.0.0 Sprint 8 新增)

用户操作审计日志。通过 `audit_middleware` 的 Flask `before_request + after_request` 双钩子在 **响应返回前** 完成记录,**审计失败仍返回原响应**(after_request 内最外层 `try/except`)。

### 19.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| user_id | Integer | INDEX | 操作用户(可为 NULL) |
| username | String(64) | | 用户名快照 |
| operation_type | String(48) | NOT NULL, INDEX | AUDIT_RULES 中定义:user_login / contract_upload / contract_review / contract_generate_preview / contract_generate / knowledge_upload / knowledge_delete / bid_upload / bid_parse / bid_requirement_submit / bid_requirement_review / bid_generate / template_upload / template_delete |
| target_type | String(32) | | 目标类型:user / contract / review / generation / document / bid / proposal / template |
| target_id | Integer | INDEX | 目标 ID |
| http_method | String(8) | | GET / POST / PUT / PATCH / DELETE |
| path | String(255) | | 请求路径(不含 query string) |
| status_code | Integer | INDEX | HTTP 状态码 |
| duration_ms | Integer | | 业务处理耗时(毫秒,after - before) |
| ip | String(64) | | 客户端 IP(优先 X-Forwarded-For) |
| summary | String(512) | | 人类可读摘要(如"合同上传成功:采购合同.pdf") |
| error_message | Text | | 失败时摘要 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间(INDEX) |

### 19.2 AUDIT_RULES 声明式匹配

```python
AUDIT_RULES = {
  'auth.login':                         ('user_login',             'user',       'response.data.user.id'),
  'contract_api.upload_contract':       ('contract_upload',        'contract',   'response.data.contract.id'),
  'contract_api.trigger_contract_review':('contract_review',       'review',     'response.data.id'),
  'generation.preview_generation':      ('contract_generate_preview','generation','response.data.generation.id'),
  'generation.generate_contract':       ('contract_generate',      'generation', 'response.data.generation.id'),
  'knowledge.upload_knowledge_document':('knowledge_upload',       'document',   'response.data.document.id'),
  'knowledge.delete_knowledge_document':('knowledge_delete',       'document',   'path.document_id'),
  'bid.upload_bid_document':            ('bid_upload',             'bid',        'response.data.bid.id'),
  'bid.parse_bid_document':             ('bid_parse',              'bid',        'path.bid_document_id'),
  'bid.submit_requirement_review':      ('bid_requirement_submit', 'bid',        'path.bid_id'),
  'bid.review_requirement':             ('bid_requirement_review', 'bid',        'path.bid_id'),
  'bid.generate_proposal':              ('bid_generate',           'proposal',   'response.data.proposal.id'),
  'template.upload_template':           ('template_upload',        'template',   'response.data.template.id'),
  'template.delete_template':           ('template_delete',        'template',   'path.template_id'),
}
```

- 未匹配 endpoints → 跳过审计,0 额外开销。
- `target_id` 提取:支持 3 种路径:`response.data.<path>` / `response.data.<obj>.id` / `path.<url_param>` / `request.json.<key>`(提取失败保留 NULL,不阻断)。
- **审计钩子仅记录业务成功/失败事实**。绝不篡改响应体、绝不 raise 到外层、绝不 `sys.exit()`。

---

## 二十、prompt_templates 表(v1.0.0 Sprint 8 新增)

Prompt 数据库管理与版本切换表。配合 `prompt_service.load_prompt()` 形成 **DB active → .md 文件 → 默认兜底** 三级回退链。**任何 DB 访问失败均自动回退 `.md`;DB + 文件均失败才走内置默认兜底;3 层全链路不抛**。

### 20.1 VALID_NAMES 枚举

| name | 用途 | 对应 Sprint |
|------|------|-------------|
| `contract_review` | Review Agent 的 system + human prompt | Sprint 5 |
| `contract_generation` | Generation Agent 的 system + human prompt | Sprint 6 |
| `bid_proposal` | Proposal Agent 的 system + human prompt | Sprint 7 |
| `bid_requirement` | Bid Requirement Extractor prompt | Sprint 7 |
| `rag_answer` | RAG Answer 生成 prompt | Sprint 4 |
| `contract_extract` | Document Pipeline 字段抽取 prompt | Sprint 3 |

### 20.2 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| name | String(64) | NOT NULL, INDEX | VALID_NAMES 之一 |
| version | String(32) | NOT NULL, DEFAULT 'v1.0' | 版本字符串(语义化 v1.0 / v1.1 / v2.0) |
| system_prompt | Text | NOT NULL | 系统提示(LLM 角色设定 + 输出约束) |
| human_prompt | Text | NOT NULL | 人类提示(变量占位用 `{{name}}`,与 Sprint 3~7 原 .md 保持一致语法) |
| description | String(512) | | 变更描述 |
| status | String(16) | NOT NULL, DEFAULT 'draft', INDEX | draft / active / inactive |
| created_by | Integer | | 创建人(admin/contract_manager) |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |
| updated_time | DateTime | NOT NULL, DEFAULT now() ON UPDATE now() | 更新时间 |

**联合约束**:`(name, version)` 唯一;**业务约束**:每个 `name` 下 **同时最多 1 条 `status=active`**(由 `activate_template()` Service 原子 UPSERT 保证,先把其他 active 置 inactive,再 set 当前 active)。

### 20.3 三级回退链(运行时)

```python
system, human = prompt_service.load_prompt(
    name='contract_review',
    fallback_file='backend/app/ai/agent/prompts/contract_review_v1.md',
    default_system='You are a helpful contract reviewer.',
    default_human='Please review: {{contract_text}}',
)
```

执行顺序:

1. **DB active Prompt**:`SELECT * FROM prompt_templates WHERE name=? AND status='active' LIMIT 1`。命中 → 返回 `(system_prompt, human_prompt)`。
2. **回退 .md 文件**:`parse_prompt_file(fallback_file)`(沿用 Sprint 3 原解析逻辑,===system=== / ===human=== 切分)。
3. **兜底 default**:传入 `default_system / default_human`(内置常量字符串,不会抛,不会为空)。

### 20.4 Prompt CRUD 状态流转

```
创建(POST /prompts, status=draft)
   │
   ├─► activate(POST /prompts/{id}/activate) ──► 其他同名 active → inactive;本 id → active
   │
   ├─► PUT 更新(description / system_prompt / human_prompt / version,仅 draft 或 inactive 允许整体覆盖;active 建议先建新版本再切换)
   │
   └─► DELETE(admin 仅;若当前为"唯一 active" 且 name 下无其他可替换版本 → 拒绝删除,防误删降级丢失)
```

---

## 二十一、evaluation_reports 表(v1.0.0 Sprint 8 新增)

AI 评估统计快照。每次 `POST /api/v1/evaluation/report` 会把当时从 `ai_request_logs` / `operation_logs` / `review_reports` / `generated_contracts` / `generated_proposals` / `analysis_tasks` 聚合的指标 JSON 快照落库,便于跨时间窗口对比。`GET /api/v1/evaluation/report` 仅内存返回,不入本表。

### 21.1 表结构

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK, AUTO_INCREMENT | 主键 |
| report_no | String(32) | NOT NULL, UNIQUE | 报告编号(EV-YYYYMMDD-####) |
| period_start | DateTime | | 统计窗口起始 |
| period_end | DateTime | | 统计窗口结束 |
| metrics | JSON | NOT NULL | 5 类指标聚合:rag / agent / tool / cost / operation |
| summary | JSON | | 高层摘要(total_ai_requests / ai_success_rate / total_operations / operation_failure_rate) |
| generated_by | Integer | | 生成人(必须 admin) |
| persisted | Boolean | NOT NULL, DEFAULT true | TRUE = 本快照(DB 行);FALSE = 仅内存,不会出现在本表 |
| created_time | DateTime | NOT NULL, DEFAULT now() | 创建时间 |

### 21.2 metrics JSON 结构(规范)

```json
{
  "rag": {
    "call_count": 62, "success_count": 60, "success_rate": 0.968,
    "avg_latency_ms": 820, "p95_latency_ms": 1630,
    "avg_total_tokens": 2150
  },
  "agent": {
    "review_total": 23, "review_success_count": 22, "contract_review_success_rate": 0.956,
    "generation_total": 18, "generation_success_count": 17, "contract_generation_success_rate": 0.944,
    "bid_total": 15, "bid_success_count": 14, "bid_proposal_success_rate": 0.933
  },
  "tool": {
    "total_calls": 376, "success_count": 370, "failed_count": 6, "success_rate": 0.984,
    "tool_breakdown": [
      {"tool_name": "KnowledgeSearchTool", "calls": 87, "success": 86, "failed": 1, "success_rate": 0.989},
      {"tool_name": "ContractFieldTool",     "calls": 23, "success": 23, "failed": 0, "success_rate": 1.000}
    ]
  },
  "cost": {
    "input_tokens": 312000, "output_tokens": 89000, "total_tokens": 401000
  },
  "operation": {
    "total_count": 537, "success_count": 516, "failed_count": 21, "failure_rate": 0.039
  }
}
```

### 21.3 聚合空值策略

所有 `COUNT() / AVG()` 在 SQLAlchemy 层使用 `.filter(...).count()`,遇到空表 → 0;遇到 `success_rate = success_count / call_count` 除零 → 显式置 0.0。**evaluation_service 不会抛 `ZeroDivisionError` / `IntegrityError`**,计算失败返回 `{call_count:0, success_rate:0}` 占位结构。

---

## 二十二、Sprint 8 数据库增量迁移说明

- **迁移策略**:纯 `ADD TABLE` 增量迁移(4 张新表)。**绝不** `ALTER ... DROP COLUMN`、绝不重建 Sprint 0~7 的任何 14 张表。
- **执行方式**:沿用 `create_app()` → `app_context()` → `db.create_all()`(SQLAlchemy 会为未存在表自动建表;已存在表 0 变更)。
- **MySQL 下**:`prompt_templates.system_prompt/human_prompt`、`operation_logs.error_message`、`ai_request_logs.error_message/trace_summary` 推荐 `LONGTEXT`(避免大 Prompt / 长 trace_summary 截断风险)。SQLite 下 TEXT 即可自动扩展。
- **索引**:4 表均对高频查询列 (name / status / user_id / created_time / related_type+related_id / operation_type / status_code) 加 INDEX。
- **数据兼容性**:旧版本(不含 Sprint 8)升级到 v1.0.0 时,启动 Flask 自动建 4 新表,0 数据迁移;旧 14 张表结构、列、索引 **完全不变**,Sprint 0~7 业务接口 100% 行为一致。
