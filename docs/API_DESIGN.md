# 智能合同与投标管理平台 API 设计文档

> **当前版本**:v1.0.0(Sprint 8 - Enterprise AI 企业级增强)
> **基础路径**:`/api/v1`
> **协议**:HTTP + JSON
> **认证**:JWT Bearer Token(Flask-JWT-Extended)
>
> **版本历史**:v0.3.0(用户认证)→ v0.4.0(合同生命周期管理)→ v0.5.0(Document Pipeline + 结构化字段)→ v0.6.0(知识库管理 + RAG 问答)→ v0.7.0(合同审核 Agent)→ v0.8.0(模板中心 + 合同生成 Pipeline)→ v0.9.0(招标文件 + Requirement 解析 + Proposal Agent + 投标 Word 生成)→ v0.9.1(Bid 企业级增强:Context Builder / Trace / Version / Review / References / Tool Stats)→ **v1.0.0(企业级:Redis Cache / AI Log / Audit Log / Prompt DB / AI Evaluation)**

---

## 一、接口设计原则

### 1.1 RESTful 规范

资源使用名词:

| 正确 | 错误 |
|------|------|
| `/contracts` | `/getContract` |
| `/users` | `/createContract` |
| `/bids` | `/uploadFile2` |

### 1.2 HTTP 方法规范

| 方法 | 用途 |
|------|------|
| GET | 查询 |
| POST | 创建 |
| PUT | 更新(整体替换) |
| PATCH | 更新(部分字段,如合同状态) |
| DELETE | 删除 |

### 1.3 统一返回格式

所有 REST JSON 接口遵循统一格式(由 `app/utils/response.py` 提供):

**成功**:

```json
{
    "code": 200,
    "message": "success",
    "data": {}
}
```

**失败**:

```json
{
    "code": 400,
    "message": "错误信息",
    "data": null
}
```

> 注:合同上传页 `/` 为 HTML 模板渲染(历史 UI 行为),不在统一 JSON 范围内。

---

## 二、认证规范

### 2.1 JWT 认证

请求头:

```
Authorization: Bearer {token}
```

示例:

```
GET /api/v1/auth/profile
Authorization: Bearer eyxxxx...
```

### 2.2 角色(v0.3.0)

| 角色 | 说明 |
|------|------|
| `admin` | 管理员 |
| `contract_manager` | 合同管理员 |
| `employee` | 员工(默认) |

> 本阶段为 Authentication(认证),非完整 RBAC。仅 `role_required()` 装饰器做角色校验,不涉及部门/权限表/菜单/组织架构。

---

## 三、用户认证模块 API(v0.3.0 新增)

**路径**:`/api/v1/auth`
**Blueprint**:`auth_bp`

### 3.1 用户注册

```
POST /api/v1/auth/register
```

**请求体**:

```json
{
    "username": "admin",
    "password": "123456",
    "role": "employee"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名(唯一,非空) |
| password | string | 是 | 密码(≥6 位,明文传输由 HTTPS 保证;服务端仅存 hash) |
| role | string | 否 | 角色,默认 `employee`;允许 `admin` / `contract_manager` / `employee` |

**成功响应**(200):

```json
{
    "code": 200,
    "message": "注册成功",
    "data": {
        "user": {
            "id": 1,
            "username": "admin",
            "role": "employee",
            "created_time": "2026-08-04 23:25:35",
            "updated_time": "2026-08-04 23:25:35"
        }
    }
}
```

**失败响应**(参数/重复用户名,400):

```json
{
    "code": 400,
    "message": "用户名已存在",
    "data": null
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 用户名为空 | 400 | 用户名不能为空 |
| 密码为空 | 400 | 密码不能为空 |
| 密码 < 6 位 | 400 | 密码长度不能少于 6 位 |
| 角色非法 | 400 | 角色非法,允许: admin, contract_manager, employee |
| 用户名已存在 | 400 | 用户名已存在 |

**安全说明**:
- 密码使用 Werkzeug `generate_password_hash` 存储,**禁止保存明文**。
- 响应中**不返回** `password_hash` 字段。

### 3.2 用户登录

```
POST /api/v1/auth/login
```

**请求体**:

```json
{
    "username": "admin",
    "password": "123456"
}
```

**成功响应**(200):

```json
{
    "code": 200,
    "message": "登录成功",
    "data": {
        "access_token": "eyJhbGciOiJIUzI1NiIs...",
        "user": {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "created_time": "2026-08-04 23:25:35",
            "updated_time": "2026-08-04 23:25:35"
        }
    }
}
```

**失败响应**(401):

```json
{
    "code": 401,
    "message": "用户名或密码错误",
    "data": null
}
```

**安全说明**:
- 用户不存在与密码错误返回**相同**的 401 信息(避免泄露用户是否存在)。
- JWT claims 携带 `role` 与 `username`,供 `role_required()` 校验。
- Access Token 默认有效期 24 小时(由 `JWT_ACCESS_TOKEN_EXPIRES` 配置,单位秒)。

### 3.3 获取当前用户信息

```
GET /api/v1/auth/profile
```

**权限**:需携带有效 JWT。

**请求头**:

```
Authorization: Bearer {access_token}
```

**成功响应**(200):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "user": {
            "id": 1,
            "username": "admin",
            "role": "admin",
            "created_time": "2026-08-04 23:25:35",
            "updated_time": "2026-08-04 23:25:35"
        }
    }
}
```

**JWT 异常响应**(统一 401):

| 场景 | code | message |
|------|------|---------|
| 未提供 Token | 401 | 未提供认证凭证 |
| Token 无效 | 401 | 无效的认证凭证 |
| Token 过期 | 401 | 认证凭证已过期,请重新登录 |
| Token 已撤销 | 401 | 认证凭证已失效 |

---

## 四、合同管理模块 API(v0.4.0 新增)

**路径**:`/api/v1/contracts`
**Blueprint**:`contract_api_bp`(独立于 `contract_bp` HTML 路由)

> 合同生命周期:Draft(草稿)→ Reviewed(已审核)→ Archived(已归档)。其余状态(Uploaded/Analyzing/Approved)预留。
> AI 分析复用 Sprint 0 已完成能力(OCR / DeepSeek),上传成功后同步调用已有分析流程。

### 4.1 上传合同

```
POST /api/v1/contracts/upload
```

**权限**:需携带有效 JWT(所有角色均可:admin / contract_manager / employee)。

**请求**:`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 合同文件(pdf / png / jpg / jpeg) |
| contract_type | string | 否 | 合同类型,默认"未分类" |
| title | string | 否 | 合同标题,默认取文件名去扩展名 |
| description | string | 否 | 描述 |

**处理流程**:

```
上传 PDF → 保存文件(uploads/contracts/{uuid}.ext)
  ↓
创建 Contract 记录(status=draft, analysis_status=processing)
  ↓
调用已有 AI 分析流程(OCR / DeepSeek)
  ↓
回写分析结果(analysis_status=completed/failed)
  ↓
返回合同信息
```

**成功响应**(200):

```json
{
    "code": 200,
    "message": "上传成功",
    "data": {
        "contract": {
            "id": 1,
            "contract_no": "CT-20260805120000-AB12CD34",
            "title": "采购合同",
            "contract_type": "采购合同",
            "description": null,
            "status": "draft",
            "file_info": { "name": "合同.pdf", "size": 1405 },
            "analysis_status": "completed",
            "analysis_result": {
                "contract_name": "...",
                "party_a": "...",
                "party_b": "...",
                "amount": "...",
                "signing_date": "..."
            },
            "creator": { "id": 1, "username": "admin", "role": "admin" },
            "creator_id": 1,
            "created_time": "2026-08-05 12:00:00",
            "updated_time": "2026-08-05 12:00:00"
        }
    }
}
```

> **注**:`file_path`(服务器内部路径)不在响应中;`analysis_status` 为 `completed` 或 `failed`(AI 失败 ≠ 上传失败,合同记录仍持久化)。

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 未携带 JWT | 401 | 未提供认证凭证 |
| 缺少 file 字段 | 400 | 未选择文件 |
| 文件名为空 | 400 | 文件名为空 |
| 文件类型不允许 | 400 | 文件类型不允许 |
| 文件超过 10MB | 413 | 上传文件过大 |

### 4.2 合同分页列表

```
GET /api/v1/contracts
```

**权限**:需携带有效 JWT。employee 仅可见 `creator_id == 自己` 的合同;admin / contract_manager 可见全部。

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码(< 1 取 1) |
| size | int | 20 | 每页数量(范围 [1, 100]) |
| keyword | string | — | 关键字(title / contract_no 模糊搜索) |
| status | string | — | 状态过滤(draft / reviewed / archived) |
| creator_id | int | — | 创建者过滤(employee 自动忽略,强制只看自己) |

**排序**:`created_time DESC`

**成功响应**(200):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "items": [
            {
                "id": 1,
                "contract_no": "CT-...",
                "title": "采购合同",
                "contract_type": "采购合同",
                "status": "draft",
                "file_info": { "name": "合同.pdf", "size": 1405 },
                "analysis_status": "completed",
                "analysis_result": null,
                "creator": { "id": 1, "username": "admin", "role": "admin" },
                "creator_id": 1,
                "created_time": "2026-08-05 12:00:00",
                "updated_time": "2026-08-05 12:00:00"
            }
        ],
        "total": 1,
        "page": 1,
        "size": 20
    }
}
```

> 列表场景 `analysis_result` 为 `null`(省略,降低负载);详情接口才返回完整结果。

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| status 非法 | 400 | 合同状态非法,允许: draft, reviewed, archived |

### 4.3 合同详情

```
GET /api/v1/contracts/{id}
```

**权限**:需携带有效 JWT。admin / contract_manager 可见任意合同;employee 仅可见自己的合同,**他人合同返回 404**(防 ID 枚举)。

**成功响应**(200):同 4.1 的 `contract` 结构,但 `analysis_result` 包含完整 AI 提取字段(读取已有结果,不重新调用 AI)。

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 合同不存在 | 404 | 合同不存在 |
| employee 访问他人合同 | 404 | 合同不存在(防枚举,不泄露存在性) |

### 4.4 更新合同状态

```
PATCH /api/v1/contracts/{id}/status
```

**权限**:仅 admin / contract_manager(employee 被 `@role_required` 拦截,返回 403)。

**请求体**:`application/json`

```json
{ "status": "reviewed" }
```

**状态机**(仅允许单向流转):

| 当前 → 目标 | draft | reviewed | archived |
|------------|:-----:|:--------:|:--------:|
| draft | 禁止 | ✅ | 禁止 |
| reviewed | 禁止 | 禁止 | ✅ |
| archived | 禁止 | 禁止 | 禁止(终态) |

**成功响应**(200):

```json
{
    "code": 200,
    "message": "状态更新成功",
    "data": { "contract": { "id": 1, "status": "reviewed", ... } }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 状态为空 | 400 | 状态不能为空 |
| 状态非法 | 400 | 合同状态非法,允许: draft, reviewed, archived |
| 非法跳转(如 draft → archived) | 400 | 非法状态跳转: draft → archived |
| 合同不存在 | 404 | 合同不存在 |
| employee 访问 | 403 | 权限不足,需要角色: admin, contract_manager |

### 4.5 权限矩阵(合同模块)

| 功能 | admin | contract_manager | employee |
|------|:-----:|:----------------:|:--------:|
| 上传合同 | √ | √ | √ |
| 查看全部合同 | √ | √ | |
| 查看自己合同 | √ | √ | √(仅自己) |
| 修改合同状态 | √ | √ | |

---

## 五、角色权限控制(v0.3.0 新增)

### 5.1 role_required 装饰器

位置:`app/decorators/role_required.py`

**用法**:

```python
from app.decorators.role_required import role_required

# 单角色
@role_required("admin")
def admin_only_view():
    ...

# 多角色(任一即可)
@role_required("admin", "contract_manager")
def manager_view():
    ...
```

**设计**:
- 基于 JWT claims 中的 `role` 字段校验。
- 内置 `@jwt_required()`,无需重复声明。
- 角色不符 → 抛 `AuthError(403)`,由全局 ErrorHandler 统一返回。

**权限不足响应**(403):

```json
{
    "code": 403,
    "message": "权限不足,需要角色: admin, contract_manager",
    "data": null
}
```

### 5.2 简化 RBAC 权限矩阵(参考)

| 功能 | admin | contract_manager | employee |
|------|:-----:|:----------------:|:--------:|
| 用户管理 | √ | | |
| 合同上传 | √ | √ | √ |
| 合同审核 | √ | √ | |
| 模板上传/启停/删除 | √ | √ | |
| 模板列表/详情(查看) | √ | √ | √(仅 active) |
| 合同生成(预览/正式) | √ | √ | √ |
| 生成记录查询/下载 | √ | √ | √(仅自己) |
| 知识库管理 | √ | √ | |
| 投标管理 | √ | √ | √ |

> 本阶段仅实现认证与 `role_required()`;完整业务权限校验将在对应业务模块(Sprint 2+)落地。

---

## 六、系统模块 API

**路径**:`/api/v1`
**Blueprint**:`system_bp`

### 6.1 健康检查

```
GET /api/v1/health
```

**响应**(200):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "status": "ok"
    }
}
```

不依赖数据库与 DeepSeek,用于部署探活。

---

## 七、合同上传页 API(历史,v0.1.0 起)

### 7.1 合同上传页

```
GET /        # 渲染上传页面(HTML)
POST /       # 上传 PDF,触发解析流程
```

**处理流程**:

```
上传 PDF
  ↓
文件保存
  ↓
PDF 文本提取(pdfplumber) / OCR(DeepSeek Vision)
  ↓
DeepSeek 合同字段提取(LangChain)
  ↓
渲染结果页面(HTML)
```

> 此接口为 HTML 渲染,非 JSON API,沿用 legacy 行为。Sprint 2 将新增 RESTful 合同管理接口。

---

## 八、Document Pipeline 模块(v0.5.0 Sprint 3 新增)

**路径前缀**:
- `/api/v1/contracts/{id}/analysis`(挂在 `contract_api_bp`)
- `/api/v1/contracts/{id}/fields`(挂在 `contract_api_bp`)
- `/api/v1/analysis/{task_id}`(新 Blueprint `analysis_bp`,前缀 `/api/v1/analysis`)

**业务服务**:`app/services/analysis_service.py`
**Pipeline 编排**:`app/ai/pipeline/runner.py`(`run_pipeline`)
**Stage 列表**:`extract → ocr → clean → chunk → llm → save`(每个 Stage 职责单一,通过 `PipelineContext` 传递数据)

### 8.1 触发合同分析

```
POST /api/v1/contracts/{id}/analysis
```

**权限**:需携带有效 JWT。admin / contract_manager 可触发任意合同;employee 仅可触发自己的合同(他人合同返回 404,防枚举)。

**请求体**:无(合同 ID 在路径中)。同合同可多次触发,每次创建一个新的 `AnalysisTask`(历史任务保留,字段以最新成功任务为准)。

**处理流程**:

```
接收请求
  ↓
校验合同存在 + 权限(复用 contract_service 权限规则)
  ↓
获取 / 创建 Document 元数据(文件 + 文本)
  ↓
创建 AnalysisTask(status=pending)
  ↓
同步执行 Pipeline(extract → ocr → clean → chunk → llm → save)
  ↓
实时回写 task.current_stage / stages_log
  ↓
回写 contract.analysis_status(success→completed / failed→failed)
  ↓
返回任务结果(含 stages_log)
```

> ⚠️ **同步执行**:Sprint 3 禁止 Celery / Redis,Pipeline 在 HTTP 请求内同步执行。前端 `axios` 超时设为 300s。大文件可能耗时较长,后续 Sprint 引入异步队列后改为立即返回 `task_id` + 轮询。

**成功响应**(200,任务执行完毕,无论 Pipeline 成功或失败):

```json
{
    "code": 200,
    "message": "分析任务已完成",
    "data": {
        "task": {
            "id": 12,
            "task_no": "AT-20260805143022-AB12CD34",
            "contract_id": 1001,
            "document_id": 5,
            "status": "success",
            "current_stage": "save",
            "stages_log": [
                {
                    "stage": "extract",
                    "status": "success",
                    "duration_ms": 320,
                    "error": null,
                    "metadata": {
                        "page_count": 3,
                        "text_length": 4521,
                        "method": "pdfplumber",
                        "has_text": true
                    }
                },
                { "stage": "ocr", "status": "skipped", "duration_ms": 0, "error": null, "metadata": {} },
                { "stage": "clean", "status": "success", "duration_ms": 12, "error": null,
                  "metadata": { "original_length": 4521, "cleaned_length": 4480, "reduced": 41 } },
                { "stage": "chunk", "status": "success", "duration_ms": 5, "error": null,
                  "metadata": { "chunk_count": 3, "total_length": 4480, "max_chunk_length": 2000, "truncated": false } },
                { "stage": "llm", "status": "success", "duration_ms": 5230, "error": null,
                  "metadata": { "attempt": 1, "field_count": 8, "found_count": 6, "null_count": 2, "avg_confidence": 0.91 } },
                { "stage": "save", "status": "success", "duration_ms": 18, "error": null,
                  "metadata": { "saved_count": 8, "found_count": 6, "null_count": 2 } }
            ],
            "error_message": null,
            "started_time": "2026-08-05T14:30:22Z",
            "finished_time": "2026-08-05T14:30:28Z",
            "created_time": "2026-08-05T14:30:22Z"
        },
        "contract": {
            "id": 1001,
            "title": "采购合同",
            "status": "draft",
            "analysis_status": "completed",
            "...": "其余字段同 4.3 合同详情"
        }
    }
}
```

**Pipeline 失败响应**(200,任务执行完毕但 Pipeline 失败):

```json
{
    "code": 200,
    "message": "分析任务执行完毕(请查看状态)",
    "data": {
        "task": {
            "id": 13,
            "task_no": "AT-20260805143105-EF56GH78",
            "status": "failed",
            "current_stage": "llm",
            "stages_log": [
                { "stage": "extract", "status": "success", "duration_ms": 280, "error": null, "metadata": { "has_text": true } },
                { "stage": "ocr", "status": "skipped", "duration_ms": 0, "error": null, "metadata": {} },
                { "stage": "clean", "status": "success", "duration_ms": 10, "error": null, "metadata": {} },
                { "stage": "chunk", "status": "success", "duration_ms": 4, "error": null, "metadata": {} },
                { "stage": "llm", "status": "failed", "duration_ms": 1200, "error": "DEEPSEEK_API_KEY 未配置,无法调用 LLM", "metadata": {} },
                { "stage": "save", "status": "skipped", "duration_ms": 0, "error": null, "metadata": {} }
            ],
            "error_message": "DEEPSEEK_API_KEY 未配置,无法调用 LLM"
        },
        "contract": { "id": 1001, "analysis_status": "failed", "...": "..." }
    }
}
```

> Stage 状态枚举:`success`(成功)/ `skipped`(跳过,前置条件不满足)/ `failed`(失败,中断 Pipeline)。

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 合同不存在 | 404 | 合同不存在 |
| employee 触发他人合同 | 404 | 合同不存在(防枚举) |
| JWT 缺失/无效 | 401 | 认证失败 |
| Pipeline 内部异常 | 200 | 任务标记为 failed,error_message 记录详情(不抛 500) |

### 8.2 查询分析任务状态

```
GET /api/v1/analysis/{task_id}
```

**权限**:需携带有效 JWT。仅任务所属合同可见的用户可查询(employee 仅能查自己合同的任务,他人任务返回 404)。

**用途**:Sprint 3 为同步执行,此接口主要用于:(1) 历史任务回溯;(2) 未来 Sprint 切换异步后供前端轮询进度。

**成功响应**(200):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "task": {
            "id": 12,
            "task_no": "AT-20260805143022-AB12CD34",
            "contract_id": 1001,
            "document_id": 5,
            "status": "success",
            "current_stage": "save",
            "stages_log": [ /* 同 8.1 stages_log 结构 */ ],
            "error_message": null,
            "triggered_by": 1,
            "started_time": "2026-08-05T14:30:22Z",
            "finished_time": "2026-08-05T14:30:28Z",
            "created_time": "2026-08-05T14:30:22Z",
            "updated_time": "2026-08-05T14:30:28Z"
        }
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 任务不存在 | 404 | 分析任务不存在 |
| employee 查询他人合同的任务 | 404 | 分析任务不存在(防枚举) |
| task_id 非整数 | 400 | 任务 ID 非法 |

### 8.3 获取合同结构化字段

```
GET /api/v1/contracts/{id}/fields
```

**权限**:需携带有效 JWT。admin / contract_manager 可查看任意合同字段;employee 仅可查看自己合同字段(他人合同返回 404,防枚举)。

**返回规则**(优先级从高到低):

1. **`contract_fields` 表**:取该合同最新一次 `status=success` 的任务的 8 个字段(若最新任务失败,回退到最近一次成功任务)。
2. **降级 `analysis_result` JSON 列**:若该合同为 Sprint 2 旧合同(无 `contract_fields` 记录但有 `analysis_result`),读取 JSON 并映射为 8 字段(`signing_date → sign_date` 映射,新字段 `contract_no` / `payment_method` / `valid_period` 补 null)。
3. **空**:两者均无,返回空字段列表 + `source=empty`。

**字段定义**(8 个,缺失返回 `null`,**禁止模型编造**):

| field_name | field_label | 说明 |
|------------|-------------|------|
| `contract_no` | 合同编号 | 合同编号 / 合同编号字段 |
| `contract_name` | 合同名称 | 合同标题 / 名称 |
| `party_a` | 甲方 | 甲方名称 |
| `party_b` | 乙方 | 乙方名称 |
| `amount` | 合同金额 | 金额数值 + 币种 |
| `sign_date` | 签署日期 | YYYY-MM-DD(无法解析则保留原文) |
| `payment_method` | 付款方式 | 付款方式描述 |
| `valid_period` | 有效期 | 有效期 / 截止日期 |

**成功响应**(200,来自 `contract_fields` 表):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "contract_id": 1001,
        "source": "contract_fields",
        "task": {
            "id": 12,
            "task_no": "AT-20260805143022-AB12CD34",
            "status": "success"
        },
        "fields": [
            {
                "field_name": "contract_no",
                "field_label": "合同编号",
                "field_value": "HT-2026-0088",
                "confidence": 0.95,
                "source_text": "合同编号:HT-2026-0088"
            },
            {
                "field_name": "contract_name",
                "field_label": "合同名称",
                "field_value": "2026 年度办公用品采购合同",
                "confidence": 0.98,
                "source_text": "甲方与乙方就 2026 年度办公用品采购..."
            },
            {
                "field_name": "party_a",
                "field_label": "甲方",
                "field_value": "XX 科技有限公司",
                "confidence": 0.92,
                "source_text": "甲方:XX 科技有限公司"
            },
            {
                "field_name": "party_b",
                "field_label": "乙方",
                "field_value": "YY 文具供应有限公司",
                "confidence": 0.92,
                "source_text": "乙方:YY 文具供应有限公司"
            },
            {
                "field_name": "amount",
                "field_label": "合同金额",
                "field_value": "人民币 100000 元(大写:壹拾万元整)",
                "confidence": 0.88,
                "source_text": "合同总金额为人民币 100000 元..."
            },
            {
                "field_name": "sign_date",
                "field_label": "签署日期",
                "field_value": "2026-07-15",
                "confidence": 0.90,
                "source_text": "双方于 2026 年 7 月 15 日签署"
            },
            {
                "field_name": "payment_method",
                "field_label": "付款方式",
                "field_value": "月结 30 天",
                "confidence": 0.85,
                "source_text": "付款方式:月结 30 天..."
            },
            {
                "field_name": "valid_period",
                "field_label": "有效期",
                "field_value": null,
                "confidence": 0.0,
                "source_text": null
            }
        ]
    }
}
```

**降级响应**(200,来自 Sprint 2 旧合同 `analysis_result` JSON):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "contract_id": 980,
        "source": "legacy_json",
        "task": null,
        "fields": [
            { "field_name": "contract_no", "field_label": "合同编号", "field_value": null, "confidence": 0.0, "source_text": null },
            { "field_name": "contract_name", "field_label": "合同名称", "field_value": "旧合同", "confidence": 0.0, "source_text": null },
            { "field_name": "party_a", "field_label": "甲方", "field_value": "旧甲方", "confidence": 0.0, "source_text": null },
            { "field_name": "party_b", "field_label": "乙方", "field_value": "旧乙方", "confidence": 0.0, "source_text": null },
            { "field_name": "amount", "field_label": "合同金额", "field_value": "50000", "confidence": 0.0, "source_text": null },
            { "field_name": "sign_date", "field_label": "签署日期", "field_value": "2026-06-01", "confidence": 0.0, "source_text": null },
            { "field_name": "payment_method", "field_label": "付款方式", "field_value": null, "confidence": 0.0, "source_text": null },
            { "field_name": "valid_period", "field_label": "有效期", "field_value": null, "confidence": 0.0, "source_text": null }
        ]
    }
}
```

**空响应**(200,无任何字段):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "contract_id": 1002,
        "source": "empty",
        "task": null,
        "fields": []
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 合同不存在 | 404 | 合同不存在 |
| employee 查看他人合同字段 | 404 | 合同不存在(防枚举) |

### 8.4 Pipeline Stage 设计说明

| Stage | 职责 | should_run 条件 | 复用 |
|-------|------|-----------------|------|
| `extract` | PDF 文本提取(pdfplumber) | `file_type == 'pdf'` | `document_service.extract_text_from_pdf` |
| `ocr` | OCR 兜底(DeepSeek Vision) | 图片文件,或 PDF 文本为空 | `ocr_service.extract_text_using_deepseek_ocr` |
| `clean` | 文本清洗(去冗余空白/换行) | 文本非空 | `text_utils.clean_text` |
| `chunk` | 文本切分(段落 + 长度上限 2000) | 文本非空 | 内置 `_split_text` |
| `llm` | LLM 结构化字段提取(8 字段 JSON) | chunks 非空 | `langchain_openai.ChatOpenAI` + Prompt v1.0 |
| `save` | 字段落库(`contract_fields`) | task 与 fields 存在 | `ContractField` 模型 |

**LLM 输出约束**:
- 必须输出结构化 JSON,字段固定为 8 个枚举值。
- 缺失字段返回 `null`,**禁止编造**。
- 每个字段附带 `confidence`(0.0~1.0)与 `source_text`(原文片段)。
- Prompt 版本化管理:`app/ai/pipeline/prompts/contract_extract_v1.md`。

### 8.5 权限矩阵(Document Pipeline 模块)

| 功能 | admin | contract_manager | employee |
|------|:-----:|:----------------:|:--------:|
| 触发任意合同分析 | √ | √ | |
| 触发自己合同分析 | √ | √ | √(仅自己) |
| 查询任务状态 | √ | √ | 仅自己合同的任务 |
| 查看合同字段 | √ | √ | 仅自己合同 |

---

## 九、知识库与 RAG 模块(v0.6.0 Sprint 4 新增)

**路径前缀**:
- `/api/v1/knowledge`(Blueprint:`knowledge_bp`)— 知识文档管理
- `/api/v1/rag`(Blueprint:`rag_bp`)— RAG 问答

**业务服务**:`app/knowledge/services/knowledge_service.py`、`app/knowledge/services/rag_service.py`
**Knowledge Layer**:`app/knowledge/`(loader / parser / chunk / embedding / vectorstore / retriever / prompts,五层解耦)

> 整体流程:知识文档上传 → Loader → Chunk(含 metadata + overlap)→ Embedding(bge-small-zh-v1.5)→ FAISS → Retriever(TopK + 阈值)→ DeepSeek → Answer
>
> 约束:仅使用 FAISS + sentence-transformers + DeepSeek;禁止 Agent / LangGraph / Redis / Celery / Elasticsearch / Milvus / pgvector。

### 9.1 上传知识文档

```
POST /api/v1/knowledge/upload
```

**权限**:仅 admin / contract_manager(`@role_required`)。employee 返回 403。

**请求**:`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 知识文档(pdf / docx / txt) |
| title | string | 否 | 文档标题(默认取文件名去扩展名,≤255 字符) |

**处理流程**:

```
校验文件类型(pdf/docx/txt)
  ↓
保存文件(uploads/knowledge/{uuid}.ext)
  ↓
创建 KnowledgeDocument(embedding_status=processing)
  ↓
parse_document → 文本 + page_map(按扩展名选 Loader)
  ↓
SemanticChunker.split → Chunk[](chunk_size=500, overlap=200, 含 metadata)
  ↓
持久化 KnowledgeChunk(每 chunk 一行,含 page_number/offset/token_count)
  ↓
embedding.encode(归一化)→ vectorstore.add(FAISS)→ 回写 vector_id
  ↓
vectorstore.save(持久化索引 + meta.json)
  ↓
更新 document.embedding_status=completed / failed
```

> ⚠️ **同步执行**:Sprint 4 禁止 Celery / Redis,Embedding + FAISS 在 HTTP 请求内同步执行。首次上传会触发模型下载(bge-small-zh-v1.5 ≈ 95MB),耗时较长;后续上传仅需 encode。前端 `axios` 超时设为 300s。
>
> **容错**:Embedding/FAISS 失败时,文档与 Chunk 仍持久化(`embedding_status=failed`),可删除后重新上传;不可检索直到重新上传成功。

**成功响应**(200,Embedding 完成):

```json
{
    "code": 200,
    "message": "上传成功,Embedding 已完成",
    "data": {
        "document": {
            "id": 3,
            "doc_no": "KD-20260805155317-E58614EA",
            "title": "合同违约条款规范",
            "source_type": "manual_upload",
            "file_info": { "name": "违约条款.txt", "size": 336, "type": "txt" },
            "page_count": 1,
            "text_length": 336,
            "chunk_count": 1,
            "embedding_status": "completed",
            "vector_indexed": true,
            "uploader": { "id": 3, "username": "manager", "role": "contract_manager" },
            "uploader_id": 3,
            "status": "active",
            "error_message": null,
            "created_time": "2026-08-05 15:53:17",
            "updated_time": "2026-08-05 15:53:39"
        }
    }
}
```

> **注**:`file_path`(服务器内部路径)不在响应中;`text_content` 默认不返回(详情接口按需返回)。

**Embedding 失败响应**(200,文档与 Chunk 已保存但不可检索):

```json
{
    "code": 200,
    "message": "上传完成,但 Embedding 失败(文档与 Chunk 已保存)",
    "data": {
        "document": {
            "id": 4,
            "doc_no": "KD-...",
            "embedding_status": "failed",
            "vector_indexed": false,
            "error_message": "Embedding 或向量入库失败(文档与 Chunk 已保存,但不可检索)"
        }
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 未携带 JWT | 401 | 未提供认证凭证 |
| employee 上传 | 403 | 权限不足,需要角色: admin, contract_manager |
| 缺少 file 字段 | 400 | 未选择文件 |
| 文件名为空 | 400 | 文件名为空 |
| 文件类型不支持 | 400 | 知识文档类型不支持,允许: pdf, docx, txt |
| 标题超过 255 字符 | 400 | 文档标题长度不能超过 255 字符 |
| 文件超过 10MB | 413 | 上传文件过大 |

### 9.2 知识文档分页列表

```
GET /api/v1/knowledge
```

**权限**:需携带有效 JWT(全部角色可查,知识库为公共知识)。

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码(< 1 取 1) |
| size | int | 20 | 每页数量(范围 [1, 100]) |
| keyword | string | — | 关键字(title / doc_no 模糊搜索) |
| embedding_status | string | — | 状态过滤(pending / processing / completed / failed) |

**排序**:`created_time DESC`,仅返回 `status=active`(排除软删)。

**成功响应**(200):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "items": [
            {
                "id": 3,
                "doc_no": "KD-20260805155317-E58614EA",
                "title": "合同违约条款规范",
                "source_type": "manual_upload",
                "file_info": { "name": "违约条款.txt", "size": 336, "type": "txt" },
                "page_count": 1,
                "text_length": 336,
                "chunk_count": 1,
                "embedding_status": "completed",
                "vector_indexed": true,
                "uploader": { "id": 3, "username": "manager", "role": "contract_manager" },
                "uploader_id": 3,
                "status": "active",
                "error_message": null,
                "created_time": "2026-08-05 15:53:17",
                "updated_time": "2026-08-05 15:53:39"
            }
        ],
        "total": 1,
        "page": 1,
        "size": 20
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| embedding_status 非法 | 400 | embedding_status 非法,允许: pending, processing, completed, failed |

### 9.3 知识文档详情

```
GET /api/v1/knowledge/{id}
```

**权限**:需携带有效 JWT(全部角色可查)。

**成功响应**(200,含 chunks 概要:前 3 个 chunk 预览):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "document": {
            "id": 3,
            "doc_no": "KD-...",
            "title": "合同违约条款规范",
            "embedding_status": "completed",
            "chunk_count": 1,
            "chunks_preview": [
                {
                    "id": 5,
                    "document_id": 3,
                    "chunk_index": 0,
                    "page_number": 1,
                    "start_offset": 0,
                    "end_offset": 336,
                    "token_count": 224,
                    "text": "合同违约条款规范全文...(预览截断到 200 字符)",
                    "metadata": null,
                    "vector_id": 0,
                    "created_time": "2026-08-05 15:53:39"
                }
            ]
        }
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 文档不存在 / 已删除 | 404 | 知识文档不存在 |
| 文档 ID 非整数 | 400 | 文档 ID 非法 |

### 9.4 删除知识文档

```
DELETE /api/v1/knowledge/{id}
```

**权限**:仅 admin / contract_manager(`@role_required`)。

**处理流程**:

```
校验存在 + 权限
  ↓
查该文档所有 chunk 的 vector_id
  ↓
从 FAISS 移除向量(若已索引)+ vectorstore.save
  ↓
清空 chunk.vector_id
  ↓
软删:document.status=deleted(记录保留;chunk 记录保留;物理文件保留)
```

> FAISS 移除失败不阻断软删:记录仍标记 `deleted`,向量可能残留(可重建索引)。

**成功响应**(200):

```json
{
    "code": 200,
    "message": "删除成功",
    "data": {
        "id": 4,
        "doc_no": "KD-20260805155340-B113A868",
        "status": "deleted"
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 文档不存在 / 已删除 | 404 | 知识文档不存在 |
| employee 删除 | 403 | 权限不足,需要角色: admin, contract_manager |

### 9.5 RAG 问答

```
POST /api/v1/rag/query
```

**权限**:需携带有效 JWT(全部角色可查)。

**请求体**:`application/json`

```json
{
    "query": "付款违约条款如何约定?"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户问题(≤1000 字符) |

**处理流程**:

```
校验 query 非空 + 长度
  ↓
retriever.retrieve(query)  # TopK=5 + 阈值=0.35
  ↓
无命中 → 返回"未找到相关内容"(不调 LLM,节省 token)
  ↓
有命中 → 关联 chunk 文本 + 构建 [文档n] 标注的 context
  ↓
加载 prompts/rag_answer.md(System + Human Prompt)
  ↓
DeepSeek 生成 answer(temperature=0.0,忠实于检索内容)
  ↓
返回 answer + references + score
```

> ⚠️ **同步执行**:检索 + LLM 可能耗时 5–30s,前端 `axios` 超时设为 120s。
>
> **Prompt 约束**(version v1.0,`app/knowledge/prompts/rag_answer.md`):仅依据检索内容回答 / 禁止编造 / 未命中明确说明 / 保留 `[文档n]` 引用标注。

**成功响应**(200,有命中 + LLM 成功):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "answer": "根据知识库内容,付款违约条款通常按日计 0.05% 违约金 [文档1]...",
        "references": [
            {
                "chunk_id": 5,
                "document_id": 3,
                "document_title": "合同违约条款规范",
                "document_label": "[文档1]",
                "chunk_index": 0,
                "page_number": 1,
                "score": 0.8234,
                "text": "合同违约条款规范全文..."
            }
        ],
        "hit_count": 1,
        "retrieval_scores": [0.8234],
        "llm_error": null
    }
}
```

**空知识库 / 无命中响应**(200,不调 LLM):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "answer": "根据现有知识库,未找到与该问题相关的内容。",
        "references": [],
        "hit_count": 0,
        "retrieval_scores": [],
        "llm_error": null
    }
}
```

**LLM 失败响应**(200,仍返回 references,answer 标注失败):

```json
{
    "code": 200,
    "message": "success",
    "data": {
        "answer": "检索到 1 条相关知识,但生成回答失败: DEEPSEEK_API_KEY 未配置,无法生成回答",
        "references": [ { "chunk_id": 5, "score": 0.8234, "...": "..." } ],
        "hit_count": 1,
        "retrieval_scores": [0.8234],
        "llm_error": "DEEPSEEK_API_KEY 未配置,无法生成回答"
    }
}
```

**异常情况**:

| 场景 | code | message |
|------|------|---------|
| 未携带 JWT | 401 | 未提供认证凭证 |
| query 为空 | 400 | 查询问题不能为空 |
| query 超过 1000 字符 | 400 | 查询问题长度不能超过 1000 字符 |
| 检索服务异常 | 200 | answer="检索服务暂时不可用,请稍后重试"(不抛 500) |

### 9.6 Knowledge Layer 架构说明

| 层 | 模块 | 职责 | 解耦方式 |
|----|------|------|---------|
| loader | `loader/{pdf,docx,txt}_loader.py` | 文件 → Page 列表 | 按 extension 注册,不依赖 chunker |
| parser | `parser/__init__.py` | Loader 编排 + page_map 构建 | 不依赖 chunker / embedding |
| chunk | `chunk/semantic_chunker.py` | 文本 → Chunk[](含 metadata + overlap) | 不依赖 embedding / vectorstore |
| embedding | `embedding/sentence_transformer_embedding.py` | 文本 → 归一化向量(bge-small-zh-v1.5) | 不依赖 vectorstore / retriever |
| vectorstore | `vectorstore/faiss_store.py` | FAISS 索引(create/save/load/add/search/delete) | 不依赖 retriever / DB |
| retriever | `retriever/dense_retriever.py` | TopK + 阈值检索(预留 Hybrid 扩展) | 依赖 vectorstore + embedding(DI 注入) |
| prompts | `prompts/rag_answer.md` | RAG 回答 Prompt v1.0(版本化) | 从代码剥离 |
| services | `services/{knowledge,rag}_service.py` | 业务编排 | 通过 registry 获取组件 |
| registry | `services/vector_store_registry.py` | 组件单例 + 启动加载 | DI 组装 |

**切分参数**(默认):
- `chunk_size`:500 字符(中文检索宜小)
- `overlap`:200 字符(相邻 chunk 重叠,保证语义连贯)
- `min_chunk_size`:100 字符(小于此合并到前一个,避免碎片)

**检索参数**(默认,可通过 `.env` 配置):
- `RETRIEVER_TOP_K`:5
- `RETRIEVER_SCORE_THRESHOLD`:0.35(归一化余弦,低于此值视为不相关)

### 9.7 权限矩阵(知识库与 RAG 模块)

| 功能 | admin | contract_manager | employee |
|------|:-----:|:----------------:|:--------:|
| 上传知识文档 | √ | √ | |
| 查看知识文档列表 | √ | √ | √ |
| 查看知识文档详情 | √ | √ | √ |
| 删除知识文档 | √ | √ | |
| RAG 问答 | √ | √ | √ |

> 知识库为公共知识,全部角色均可查询与 RAG 问答;仅 admin / contract_manager 可上传 / 删除。

---

## 十、合同审核模块 API(v0.7.0 Sprint 5 新增)

合同 AI 风险审核模块,基于手写 ReAct Agent(LLM 决策 + 3 个无状态 Tool 执行)生成结构化风险报告。

**模块路径**:`/api/v1/reviews`(独立 Blueprint)+ `/api/v1/contracts/{id}/review`(挂 contract_api_bp)

**Agent 架构**:

```
POST /contracts/{id}/review
  → review_service.trigger_review
    → 创建 ReviewReport(pending → running)
    → ContractReviewAgent.run(ReAct 循环)
      → LLM 决策(call_tool / final_report)
      → Tool 执行:
          - contract_field_tool  (复用 Sprint 3 analysis_service)
          - knowledge_search_tool(复用 Sprint 4 Retriever)
          - risk_rule_tool       (11 条确定性规则)
    → 落库 risks / risk_level / summary / tool_calls_log
    → commit(success / failed)
```

**容错策略**:LLM 不可用 / 迭代上限 → 走 `risk_rule_tool` 兜底生成报告,ReviewReport 标记 success 但 summary 注明 LLM 不可用,接口仍 200。

### 10.1 触发合同 AI 风险审核

```
POST /api/v1/contracts/{contract_id}/review
```

**权限**:`admin` / `contract_manager`(employee 返回 403)

**前置条件**:合同 `analysis_status = completed`(否则返回 400 BusinessError)

**请求**:无 body

**响应**(200):

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "review": {
      "id": 1,
      "review_no": "RV-20260806172808-7AD29C47",
      "contract_id": 2,
      "task_id": 5,
      "status": "success",
      "risk_level": "high",
      "summary": "基于规则检查生成(5 条风险)。注:LLM 不可用...",
      "risks": [
        {
          "type": "付款风险",
          "severity": "medium",
          "description": "合同未明确付款方式,存在付款条款模糊风险",
          "suggestion": "建议补充明确的付款方式、付款节点与付款周期",
          "evidence": "付款方式字段缺失",
          "rule_id": "R001",
          "references": []
        }
      ],
      "tool_calls_log": [
        {
          "tool": "risk_rule_tool",
          "args": {},
          "duration_ms": 110,
          "summary": "兜底:返回 5 条风险",
          "error": null
        }
      ],
      "iterations": 1,
      "llm_error": "LLM 调用失败,请稍后重试",
      "started_time": "2026-08-06 17:28:08",
      "finished_time": "2026-08-06 17:28:09",
      "created_time": "2026-08-06 17:28:08"
    },
    "contract": {
      "id": 2,
      "title": "采购合同",
      "contract_no": "C-2026-001"
    }
  }
}
```

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 合同未完成 AI 分析(analysis_status != completed) |
| 403 | employee 触发审核 |
| 404 | 合同不存在 |

### 10.2 查询合同审核历史

```
GET /api/v1/contracts/{contract_id}/reviews?page=1&size=20
```

**权限**:JWT(employee 仅可见自己合同的审核,他人合同返回 404 防枚举)

**响应**(200):

```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "id": 1,
        "review_no": "RV-20260806172808-7AD29C47",
        "status": "success",
        "risk_level": "high",
        "iterations": 1,
        "created_time": "2026-08-06 17:28:08"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

### 10.3 全局审核报告列表

```
GET /api/v1/reviews?page=1&size=20&risk_level=high&status=success
```

**权限**:JWT(employee 仅可见自己合同的审核)

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码,默认 1 |
| size | int | 否 | 每页数量,默认 20,最大 100 |
| risk_level | string | 否 | 风险等级过滤:high / medium / low / none |
| status | string | 否 | 状态过滤:pending / running / success / failed |

**响应**(200):

```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "id": 1,
        "review_no": "RV-20260806172808-7AD29C47",
        "contract_id": 2,
        "status": "success",
        "risk_level": "high",
        "iterations": 1,
        "contract": {
          "id": 2,
          "title": "采购合同",
          "contract_no": "C-2026-001"
        },
        "created_time": "2026-08-06 17:28:08"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | risk_level / status 非法枚举值 |

### 10.4 查询审核报告详情

```
GET /api/v1/reviews/{review_id}
```

**权限**:JWT(employee 仅可查自己合同的审核,他人返回 404 防枚举)

**响应**(200):

```json
{
  "code": 200,
  "data": {
    "review": {
      "id": 1,
      "review_no": "RV-20260806172808-7AD29C47",
      "contract_id": 2,
      "task_id": 5,
      "status": "success",
      "risk_level": "high",
      "summary": "基于规则检查生成(5 条风险)...",
      "risks": [
        {
          "type": "付款风险",
          "severity": "medium",
          "description": "...",
          "suggestion": "...",
          "evidence": "...",
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
      ],
      "tool_calls_log": [...],
      "iterations": 1,
      "llm_error": null,
      "error_message": null,
      "triggered_by": 2,
      "started_time": "2026-08-06 17:28:08",
      "finished_time": "2026-08-06 17:28:09",
      "created_time": "2026-08-06 17:28:08",
      "updated_time": "2026-08-06 17:28:09"
    }
  }
}
```

**risks 字段结构**:

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | 风险类型:付款风险 / 金额风险 / 期限风险 / 关键条款缺失 / 其他 |
| severity | string | 严重度:high / medium / low |
| description | string | 风险描述 |
| suggestion | string | 修改建议 |
| evidence | string | 风险依据(字段值 / 规则触发条件) |
| rule_id | string | 触发的规则 ID(R001-R011,LLM 综合风险可能无) |
| references | array | 知识库引用来源(document_title / chunk_id / page_number / score) |

**异常**:

| code | 触发场景 |
|------|---------|
| 404 | 审核报告不存在 / employee 查看他人合同审核 |

### 10.5 风险等级与状态枚举

**审核状态**(status):

| 值 | 说明 |
|----|------|
| pending | 待执行 |
| running | 执行中 |
| success | 已完成 |
| failed | 审核失败 |

**风险等级**(risk_level):

| 值 | 说明 | 触发条件 |
|----|------|---------|
| high | 高风险 | 含 high severity 风险 |
| medium | 中风险 | 含 medium severity 风险(无 high) |
| low | 低风险 | 仅含 low severity 风险 |
| none | 无风险 | 无任何风险 |

**风险类型**(type)与规则 ID:

| 规则 ID | 类型 | 严重度 | 触发条件 |
|---------|------|--------|---------|
| R001 | 付款风险 | medium | 付款方式缺失 |
| R002 | 付款风险 | high | 付款周期 ≥ 30 天 |
| R003 | 金额风险 | high | 合同金额缺失 |
| R004 | 金额风险 | medium | 金额 ≤ 0 |
| R005 | 期限风险 | medium | 有效期缺失 |
| R006 | 期限风险 | medium | 签署日期缺失 |
| R007 | 期限风险 | medium | 有效期与签署日期矛盾 |
| R008 | 关键条款缺失 | high | 缺违约责任条款 |
| R009 | 关键条款缺失 | medium | 缺争议解决条款 |
| R010 | 关键条款缺失 | medium | 缺不可抗力条款 |
| R011 | 关键条款缺失 | low | 缺合同期限条款 |

### 10.6 查询 Agent 执行 Trace(v0.7.1 新增)

```
GET /api/v1/reviews/{id}/trace
```

**权限**:需携带有效 JWT。admin / contract_manager 可查任意审核;employee 仅可查自己合同的审核(他人返回 404)。

**用途**:供前端 ReviewDetail 页 Agent 执行过程 Timeline 展示(Thought → Decision → Action → Observation → Duration → Status)。

**成功响应**(200):

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "trace": {
      "id": 1,
      "review_no": "RV-20260806020956-AB12CD34",
      "contract_id": 999,
      "status": "success",
      "risk_level": "high",
      "iterations": 3,
      "agent_trace": [
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
      ],
      "trace_summary": {
        "steps": 6,
        "total_duration_ms": 7590,
        "llm_duration_ms": 7233,
        "tool_duration_ms": 357,
        "tool_stats": {
          "risk_rule_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 151},
          "knowledge_search_tool": {"call_count": 1, "success_count": 1, "failed_count": 0, "total_ms": 199}
        },
        "llm_stats": {"call_count": 3, "total_ms": 7233, "error": null},
        "iterations": 3,
        "max_iterations": 5,
        "iteration_exceeded": false
      },
      "llm_error": null,
      "llm_error_type": null,
      "started_time": "2026-08-06 02:09:56",
      "finished_time": "2026-08-06 02:10:04"
    }
  }
}
```

**agent_trace 每步字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| step | int | 步骤序号(从 1 开始) |
| thought | string | LLM 思考内容(这一步想做什么) |
| decision | string | 决策理由(为什么选择这个 Tool / 为什么输出最终报告) |
| action | string | 动作类型(llm_call / call_tool / final_report / system / iteration_exceeded / fallback) |
| tool_name | string | Tool 名称(action=call_tool 时填) |
| tool_input | object | Tool 输入参数 |
| observation | any | 观察结果(Tool 返回摘要 / LLM 响应摘要) |
| start_time | string | 开始时间(ISO 8601) |
| end_time | string | 结束时间(ISO 8601) |
| duration_ms | int | 耗时(毫秒) |
| status | string | 状态(success / failed / skipped) |
| error_message | string | 错误信息(失败时填) |

**LLM 错误类型**(llm_error_type):

| 值 | 说明 | Fallback |
|----|------|---------|
| timeout | LLM 调用超时 | ✅ RiskRuleTool |
| rate_limit | 429 限流 | ✅ RiskRuleTool |
| server_error | 5xx 服务端错误 | ✅ RiskRuleTool |
| network | 网络异常 | ✅ RiskRuleTool |
| auth | API Key 无效 / 未配置 | ✅ RiskRuleTool |
| framework | langchain 未安装 | ✅ RiskRuleTool |
| json_parse | LLM 输出 JSON 解析失败 | ✅ RiskRuleTool |
| null | 无错误(LLM 成功调用) | — |

**异常**:

| code | 触发场景 |
|------|---------|
| 404 | 审核报告不存在 / employee 查看他人合同审核 |

---

## 十一、合同生成模块 API(v0.8.0 Sprint 6 新增)

AI 合同自动生成系统,构建完整的 Template → AI → Word → Contract 生成流水线。模板中心管理 Word 模板(`{{variable}}` 占位符自动解析);Generation Agent(手写 ReAct,4 个无状态 Tool)按需补充付款/违约/保密/知识产权/售后条款;docxtpl 渲染保留模板样式;生成成功后自动创建合同记录,形成"生成→解析→审核"闭环。**不修改** Sprint 3/4/5 任何核心逻辑,仅通过公开 Service / Tool 复用。

**模块路径**:
- `/api/v1/templates`(独立 Blueprint `template_bp`,模板管理)
- `/api/v1/generation`(独立 Blueprint `generation_bp`,合同生成 Pipeline)
- `/api/v1/generated`(独立 Blueprint `generated_download_bp`,Word 下载)

**Generation Pipeline 架构**:

```
POST /generation/preview | /generation/generate
  → generation_service.preview_generation | generate_contract
    → 加载模板 + 校验变量
    → 创建 GeneratedContract(pending → running)
    → GenerationAgent.run(ReAct 循环,max_iterations=5)
        → LLM 决策(call_tool / final_report)
        → Tool 执行:
            - template_tool          (模板变量查询,新建)
            - knowledge_search_tool  (复用 Sprint 4 Retriever)
            - clause_generation_tool (调 DeepSeek 生成条款,新建)
            - contract_rule_tool     (确定性规则校验:缺失字段 + 风险条款,不调 LLM,新建)
    → 落库 clauses / rag_references / validation_results / agent_trace
    → [仅 generate] word_renderer.render_contract(docxtpl + python-docx)
    → [仅 generate] contract_service.create_contract_from_generation()
    → commit(success / failed)
```

**容错策略**:LLM 不可用 → Agent 走兜底(仅 `contract_rule_tool`,无 AI 条款),仍渲染 Word + 建合同,接口不失败(GeneratedContract 标记 success,`llm_error` 记录原因)。

**同步执行**:Sprint 6 不引入 Celery / Redis / LangGraph,Agent 在 HTTP 请求内同步完成;`/generate` 接口耗时 15–90s,前端应设超时 300s。

### 11.1 模板分页列表

```
GET /api/v1/templates
```

**权限**:JWT(全部角色;employee 仅可见 `active` 模板)

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| page | int | 否 | 页码,默认 1 |
| size | int | 否 | 每页数量,默认 20,最大 100 |
| keyword | string | 否 | 关键字(name / template_no 模糊搜索) |
| status | string | 否 | `active` / `disabled`(employee 强制 `active`) |
| contract_type | string | 否 | 合同类型过滤 |
| version | string | 否 | 模板版本过滤(精确匹配,如 `v1.0`;v0.8.1 补充) |

**响应**(200):

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 1,
        "template_no": "TPL-20260806184500-7AD29C47",
        "name": "采购合同模板",
        "description": "标准采购合同",
        "contract_type": "采购合同",
        "file_info": {"name": "purchase.docx", "size": 38120},
        "variable_count": 6,
        "version": "v1.0",
        "status": "active",
        "creator": {"id": 1, "username": "admin", "role": "admin"},
        "creator_id": 1,
        "created_time": "2026-08-06 18:45:00",
        "updated_time": "2026-08-06 18:45:00"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

> 列表场景不返回 `variables` 详情(仅 `variable_count`),减少响应体积;详情接口 11.3 返回完整变量清单。

### 11.2 上传模板

```
POST /api/v1/templates/upload
```

**权限**:`admin` / `contract_manager`(employee 返回 403)

**请求**:`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| file | file | 是 | 模板文件(`.docx`) |
| name | string | 否 | 模板名称(默认取文件名去扩展名) |
| description | string | 否 | 模板说明 |
| contract_type | string | 否 | 合同类型(默认"未分类") |
| version | string | 否 | 模板版本(默认 `v1.0`;用于区分同名模板的不同迭代版本,v0.8.1 补充) |

**流程**:保存 .docx → `docxtpl.get_undeclared_template_variables()` 解析 `{{variable}}` → 建模板记录(`status=active`)

**响应**(200):

```json
{
  "code": 200,
  "message": "模板上传成功",
  "data": {
    "template": {
      "id": 1,
      "template_no": "TPL-20260806184500-7AD29C47",
      "name": "采购合同模板",
      "description": "标准采购合同",
      "contract_type": "采购合同",
      "file_info": {"name": "purchase.docx", "size": 38120},
      "variables": [
        {"name": "party_a", "label": "甲方", "required": true, "sample": "采购方公司"},
        {"name": "party_b", "label": "乙方", "required": true, "sample": "供货方公司"},
        {"name": "amount", "label": "金额", "required": true, "sample": "100000"},
        {"name": "sign_date", "label": "签署日期", "required": false, "sample": "2026-08-06"}
      ],
      "variable_count": 4,
      "version": "v1.0",
      "status": "active",
      "creator": {"id": 1, "username": "admin", "role": "admin"},
      "creator_id": 1,
      "created_time": "2026-08-06 18:45:00",
      "updated_time": "2026-08-06 18:45:00"
    }
  }
}
```

> `variables` 每项结构:`{name, label, required, sample}`;`label` 默认取 `name`,`required` 默认 `false`,`sample` 由 docxtpl 解析得出(可能为 null)。
> `version`(v0.8.1 补充):模板版本,默认 `v1.0`,用于区分同名模板的不同迭代版本;列表与详情接口均返回该字段。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 未选择文件 / 文件名为空 / 非 .docx 文件 / 模板损坏无法解析 |
| 403 | employee 角色尝试上传 |
| 413 | 文件超过 10MB |

### 11.3 模板详情

```
GET /api/v1/templates/{template_id}
```

**权限**:JWT(admin / manager 可见任意;employee 仅可见 `active`,disabled 返回 404 防枚举)

**响应**(200):返回完整模板信息(含 `variables` 数组),结构与 11.2 响应中 `template` 一致。

**异常**:

| code | 触发场景 |
|------|---------|
| 404 | 模板不存在 / employee 查看 disabled 模板 |

### 11.4 启停模板

```
PATCH /api/v1/templates/{template_id}/status
```

**权限**:`admin` / `contract_manager`(employee 返回 403)

**请求体**:

```json
{"status": "disabled"}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| status | string | 是 | `active` / `disabled`(`active ⇄ disabled` 可反复切换,幂等) |

**响应**(200):返回更新后的模板(结构与 11.3 一致),`message="模板状态更新成功"`。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | status 为空 / 非法值 |
| 404 | 模板不存在 |

### 11.5 删除模板

```
DELETE /api/v1/templates/{template_id}
```

**权限**:`admin` / `contract_manager`(employee 返回 403)

**约束**:若模板已被用于生成(存在 `generated_contracts` 记录),**禁止删除**,提示"已有生成记录,建议停用"。删除为硬删除(连同 .docx 文件一起清理)。

**响应**(200):

```json
{
  "code": 200,
  "message": "模板删除成功",
  "data": null
}
```

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 模板已有生成记录,拒绝删除 |
| 404 | 模板不存在 |

### 11.6 预览生成结果

```
POST /api/v1/generation/preview
```

**权限**:JWT(全部角色均可;任务书"普通用户仅可使用模板"指使用权限)

**请求体**:

```json
{
  "template_id": 1,
  "input_variables": {
    "party_a": "采购方公司",
    "party_b": "供货方公司",
    "amount": "100000",
    "sign_date": "2026-08-06"
  },
  "contract_type": "采购合同"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| template_id | int | 是 | 模板 ID |
| input_variables | object | 是 | 用户填写的变量键值对 |
| contract_type | string | 否 | 合同类型(默认取模板类型) |

**流程**:加载模板 + 校验变量 → 创建 GeneratedContract(`status=running`,不落库 file)→ 执行 Generation Agent → 落库 clauses / references / validation / trace → **不渲染 Word,不建合同**

**响应**(200):

```json
{
  "code": 200,
  "message": "预览生成完成",
  "data": {
    "generation": {
      "id": 12,
      "generation_no": "GC-20260806190000-7AD29C47",
      "template_id": 1,
      "contract_id": null,
      "status": "success",
      "input_variables": {"party_a": "采购方公司", "amount": "100000"},
      "generated_clauses": [
        {
          "name": "付款条款",
          "content": "甲方应在收到乙方开具的合规发票后 30 日内...",
          "source": "clause_generation_tool",
          "references": [
            {"document_title": "采购合同规范", "chunk_id": 5, "page_number": 2, "score": 0.89}
          ]
        }
      ],
      "rag_references": [
        {"document_title": "采购合同规范", "chunk_id": 5, "page_number": 2, "score": 0.89}
      ],
      "validation_results": {
        "passed": true,
        "issues": []
      },
      "file_info": null,
      "agent_trace": [...],
      "trace_summary": {...},
      "iterations": 3,
      "llm_error": null,
      "llm_error_type": null,
      "error_message": null,
      "template": {"id": 1, "name": "采购合同模板", "template_no": "TPL-...", "contract_type": "采购合同"},
      "started_time": "2026-08-06 19:00:00",
      "finished_time": "2026-08-06 19:00:18"
    }
  }
}
```

> 预览记录 `contract_id=null` / `file_info=null`,可在生成记录列表中按 `status=success` 查到,但不可下载(无文件)。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | template_id 为空 / 模板已 disabled / 必填变量缺失 |
| 404 | 模板不存在 / employee 查询 disabled 模板 |

### 11.7 正式生成合同

```
POST /api/v1/generation/generate
```

**权限**:JWT(全部角色均可)

**请求体**:

```json
{
  "template_id": 1,
  "input_variables": {
    "party_a": "采购方公司",
    "party_b": "供货方公司",
    "amount": "100000",
    "sign_date": "2026-08-06"
  },
  "contract_type": "采购合同",
  "title": "采购合同-2026年8月",
  "description": "AI 自动生成"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| template_id | int | 是 | 模板 ID |
| input_variables | object | 是 | 用户填写的变量键值对 |
| contract_type | string | 否 | 合同类型(默认取模板类型) |
| title | string | 否 | 合同标题(默认取模板名 + 日期) |
| description | string | 否 | 合同描述(默认"AI 自动生成") |

**流程**:
1. 加载并校验模板(active 状态)
2. 校验输入变量(必填项)
3. 创建 GeneratedContract(`status=running`)
4. 同步执行 Generation Agent(ReAct 循环,`max_iterations=5`)
5. `word_renderer.render_contract`(docxtpl 填充变量 + python-docx 插入 AI 条款段落,保留模板样式)
6. `contract_service.create_contract_from_generation`(创建 Contract,`status=draft` / `analysis_status=pending`,回填 `generated_contracts.contract_id`)
7. 落库生成结果(`status=success`,`file_path` / `contract_id` / `agent_trace`)

**响应**(200):

```json
{
  "code": 200,
  "message": "合同生成成功,已自动创建合同记录",
  "data": {
    "generation": {
      "id": 13,
      "generation_no": "GC-20260806191000-9BEF12AA",
      "template_id": 1,
      "contract_id": 25,
      "status": "success",
      "input_variables": {"party_a": "采购方公司", "amount": "100000"},
      "generated_clauses": [...],
      "rag_references": [...],
      "validation_results": {"passed": true, "issues": []},
      "file_info": {"name": "GC-20260806191000-9BEF12AA.docx", "size": 38120},
      "agent_trace": [...],
      "trace_summary": {...},
      "iterations": 4,
      "llm_error": null,
      "template": {"id": 1, "name": "采购合同模板", "template_no": "TPL-...", "contract_type": "采购合同"},
      "contract": {"id": 25, "contract_no": "CT-20260806191000-9BEF12AA", "title": "采购合同-2026年8月", "status": "draft"},
      "started_time": "2026-08-06 19:10:00",
      "finished_time": "2026-08-06 19:11:32"
    },
    "contract": {
      "id": 25,
      "contract_no": "CT-20260806191000-9BEF12AA",
      "title": "采购合同-2026年8月",
      "contract_type": "采购合同",
      "status": "draft",
      "analysis_status": "pending",
      "creator_id": 1
    }
  }
}
```

> 生成的合同自动进入合同管理中心,可继续触发 Sprint 3 AI 解析(详情页"开始分析"按钮)与 Sprint 5 合同审核("AI 风险审核"按钮),形成"生成→解析→审核"闭环。

**容错**:
- Agent 失败(LLM 不可用)→ 走兜底(无 AI 条款),仍渲染 Word + 建合同,GeneratedContract 标记 `success`,`llm_error` 字段记录原因,接口仍 200
- Word 渲染失败 → GeneratedContract 标记 `failed`,不建合同,返回错误信息
- 建合同失败 → GeneratedContract 标记 `failed`,清理已生成的 Word 文件,返回错误信息

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | template_id 为空 / 模板已 disabled / 必填变量缺失 |
| 404 | 模板不存在 / employee 查询 disabled 模板 |
| 500 | Word 渲染失败 / 建合同失败(GeneratedContract 已落库为 failed) |

### 11.8 生成记录分页列表

```
GET /api/v1/generation/history
```

**权限**:JWT(admin / manager 可见全部;employee 仅可见自己触发的)

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| page | int | 否 | 页码,默认 1 |
| size | int | 否 | 每页数量,默认 20,最大 100 |
| status | string | 否 | `pending` / `running` / `success` / `failed` |
| template_id | int | 否 | 模板过滤 |

**响应**(200):

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": 13,
        "generation_no": "GC-20260806191000-9BEF12AA",
        "template_id": 1,
        "contract_id": 25,
        "status": "success",
        "iterations": 4,
        "file_info": {"name": "GC-...docx", "size": 38120},
        "template": {"id": 1, "name": "采购合同模板", "template_no": "TPL-...", "contract_type": "采购合同"},
        "contract": {"id": 25, "contract_no": "CT-...", "title": "采购合同-2026年8月", "status": "draft"},
        "triggered_by": 1,
        "started_time": "2026-08-06 19:10:00",
        "finished_time": "2026-08-06 19:11:32",
        "created_time": "2026-08-06 19:10:00"
      }
    ],
    "total": 1,
    "page": 1,
    "size": 20
  }
}
```

> 列表场景不返回 `generated_clauses` / `rag_references` / `validation_results` / `agent_trace`(详情接口 11.9 返回)。

### 11.9 生成记录详情

```
GET /api/v1/generation/{generation_id}
```

**权限**:JWT(admin / manager 可查任意;employee 仅可查自己触发的,他人返回 404)

**响应**(200):返回完整生成记录,包含 `generated_clauses` / `rag_references` / `validation_results` / `agent_trace` / `trace_summary` / `template` 摘要 / `contract` 摘要(成功时)。结构同 11.7 响应中 `generation` 字段。

**异常**:

| code | 触发场景 |
|------|---------|
| 404 | 生成记录不存在 / employee 查询他人记录 |

### 11.10 生成记录 Agent Trace

```
GET /api/v1/generation/{generation_id}/trace
```

**权限**:JWT(admin / manager 可查任意;employee 仅可查自己触发的,他人返回 404)

**用途**:供前端 `GenerationDetail` 页 Agent 执行过程 Timeline 展示(Thought → Decision → Action → Observation → Duration → Status)。

**响应**(200):

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "trace": {
      "id": 13,
      "generation_no": "GC-20260806191000-9BEF12AA",
      "template_id": 1,
      "contract_id": 25,
      "status": "success",
      "iterations": 4,
      "agent_trace": [
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
      ],
      "trace_summary": {
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
      },
      "llm_error": null,
      "llm_error_type": null,
      "started_time": "2026-08-06 19:10:00",
      "finished_time": "2026-08-06 19:11:32"
    }
  }
}
```

> Trace 结构与 Sprint 5 ReviewReport 一致(复用 `_safe_serialize`);每步 12 字段:`step / thought / decision / action / tool_name / tool_input / observation / start_time / end_time / duration_ms / status / error_message`。

### 11.11 下载生成的 Word 文档

```
GET /api/v1/generated/{generation_id}/download
```

**权限**:JWT(admin / manager 可下载任意;employee 仅可下载自己触发的)

**前置条件**:生成记录 `status = success`(预览 / 失败记录无文件 → 400);文件物理存在

**响应**(200):Word 文件下载流

```
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="GC-20260806191000-9BEF12AA.docx"
```

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 生成记录 status != success / 文件丢失 |
| 404 | 生成记录不存在 / employee 下载他人文件 |

---

## 十二、招投标管理模块 API(v0.9.0 Sprint 7 新增)

### 12.1 模块概述

Sprint 7 构建 AI 招投标闭环:招标文件 → 结构化 Requirement → Bid Agent → 投标方案 → Word 文件。模块由 **两个 Blueprint** 组成:

| Blueprint | 前缀 | 职责 |
|----------|------|------|
| `bid_bp` | `/api/v1/bids` | 招标文件管理(上传/列表/详情/删除/重解析/需求查询/生成投标) |
| `proposal_bp` | `/api/v1/proposals` | 投标生成记录管理(列表/详情/Trace/下载) |

**分层约束**(沿用 Sprint 0~6):

```
HTTP Request
  ↓
api/bid/routes.py        参数接收 / JWT 校验 / 角色校验 / 返回统一 Response
  ↓
services/bid_service.py  招标业务(上传/落库/Pipeline 调度/删除守卫)
services/proposal_service.py  投标业务(Agent 调度/Word 渲染/单事务落库)
  ↓
ai/bid/pipeline.py       Bid Pipeline(复用 Sprint 3 提取 + LLM 抽 15 字段)
ai/bid/proposal_agent.py Proposal Agent(手写 ReAct,5 个无状态 Tool)
ai/bid/proposal_renderer.py  Word 渲染(复用 Sprint 6 docxtpl + python-docx)
  ↓
models/bid_document.py / bid_requirement.py / generated_proposal.py / proposal_section.py
```

**禁止**:API 层直接访问数据库 / 调用 Agent / 调用 LLM / 渲染 Word / 执行 Pipeline。

**复用关系**(只读 import,不修改核心):
- Sprint 3:`extract_text_from_pdf` / `extract_text_using_deepseek_ocr` / `clean_text` / `SemanticChunker`
- Sprint 4:`vector_store_registry.retriever` / `rag_service._build_context_and_references`
- Sprint 5:`BaseTool` / `ToolRegistry` / `call_deepseek` / `_safe_serialize`(Trace 结构)
- Sprint 6:`cleanup_generated_file` / Word 渲染模式 / 单事务 Service 模式

### 12.2 上传招标文件

```
POST /api/v1/bids/upload
```

**权限**:JWT(任意角色;employee 仅后续可见自己上传的)

**请求**:`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| file | file | 是 | 招标文件(pdf / png / jpg / jpeg) |
| title | string | 否 | 招标标题(默认取文件名去扩展名) |

**同步执行 Bid Pipeline**(耗时 5–30s,前端建议超时 120s):

```
保存文件(UUID 命名,uploads/bids/)
  ↓
落库 BidDocument(parse_status=pending)
  ↓
Bid Pipeline:
  PDF 文本提取(pdfplumber) / 图片 OCR(DeepSeek-VL)
    ↓
  文本清洗(clean_text)
    ↓
  Chunk 切分(SemanticChunker,长文档)
    ↓
  LLM 抽取 15 字段(DeepSeek,requirement_extractor)
  ↓
落库 BidRequirement(1:1,UPSERT)
  ↓
回写 parse_status=success / failed
```

**响应**(200,`parse_status=success`):

```json
{
  "code": 200,
  "message": "招标文件上传成功,需求解析完成",
  "data": {
    "bid_document": {
      "id": 1,
      "bid_no": "BD-20260807013000-A1B2C3D4",
      "title": "XX 项目招标文件",
      "file_info": {"name": "tender.pdf", "size": 524288, "type": "pdf"},
      "page_count": 12,
      "text_length": 18234,
      "parse_status": "success",
      "extract_method": "pdfplumber",
      "uploader": {"id": 1, "username": "admin", "role": "admin"},
      "requirement": {
        "requirement_no": "BR-20260807013001-E5F6G7H8",
        "status": "success",
        "project_name": "XX 智能化采购项目",
        "budget": "5000000",
        "deadline": "2026-09-15",
        "field_count": 13,
        "missing_count": 2,
        "confidence": 0.88
      }
    }
  }
}
```

> Pipeline 失败不报错,返回 `parse_status=failed` + `error_message`,前端可调用 `/parse` 重试。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 未选择文件 / 文件名为空 / 文件类型不支持 |
| 413 | 文件超过 10MB |

### 12.3 招标文件列表

```
GET /api/v1/bids
```

**权限**:JWT(admin / manager 全部;employee 仅自己上传的)

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| size | int | 20 | 每页数量(最大 100) |
| status | string | - | 解析状态过滤(pending / processing / success / failed) |
| keyword | string | - | title / bid_no 模糊搜索 |

**响应**(200):`data.items` 含招标文件列表(含 requirement 概要,不含全文)。

### 12.4 招标文件详情

```
GET /api/v1/bids/{bid_document_id}
```

**权限**:JWT(admin / manager 任意;employee 仅自己上传的,他人返回 404)

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| include_text | bool | false | 是否返回 `text_content` 全文 |

**响应**(200):招标文件详情(含 requirement 概要;`include_text=true` 时返回全文)。

**异常**:404 招标文件不存在 / employee 查询他人资源。

### 12.5 删除招标文件

```
DELETE /api/v1/bids/{bid_document_id}
```

**权限**:`admin` / `contract_manager`(employee 返回 403)

**流程**:校验存在 → 校验无关联 `GeneratedProposal`(若有,返回 400 提示先删除生成记录)→ cascade 删除 `BidRequirement` → 物理删除文件。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 有关联投标生成记录,需先删除 |
| 403 | employee 尝试删除 |
| 404 | 招标文件不存在 |

### 12.6 重新解析招标文件

```
POST /api/v1/bids/{bid_document_id}/parse
```

**权限**:JWT(admin / manager 任意;employee 仅自己上传的)

**场景**:首次解析失败(LLM 不可用 / OCR 失败)后重试。复用已落库文件,UPSERT `BidRequirement`(1:1,UPDATE 原行)。

**异常**:404 招标文件不存在 / employee 操作他人资源。

### 12.7 查询招标需求

```
GET /api/v1/bids/{bid_document_id}/requirement
```

**权限**:JWT(admin / manager 任意;employee 仅自己上传的)

**响应**(200):返回 15 字段 Requirement JSON + 质量指标:

| 字段 | 类型 | 说明 |
|------|------|------|
| project_name | string | 项目名称 |
| tender_org | string | 招标单位 |
| project_location | string | 项目地点 |
| budget | string | 预算金额 |
| deadline | string | 投标截止时间 |
| duration | string | 工期 / 服务期 |
| delivery_requirements | string | 供货范围 / 交货要求 |
| technical_requirements | string[] | 技术要求清单 |
| qualification_requirements | string[] | 资格要求清单 |
| scoring_criteria | string[] | 评分标准 |
| bid_opening_time | string | 开标时间 |
| bid_validity | string | 投标有效期 |
| payment_terms | string | 付款条件 |
| contact | string | 联系人 / 电话 |
| other | string | 其他补充 |

> 另含质量指标 `field_count` / `missing_count` / `confidence`(0–1)。

### 12.8 生成投标文件

```
POST /api/v1/bids/{bid_document_id}/generate
```

**权限**:JWT(任意角色;employee 仅自己上传的招标文件可生成)

**请求体**:`application/json`(可选)

```json
{
  "input_data": {
    "company_profile_overrides": {"公司名称": "XX 科技有限公司"},
    "options": {"include_summary": true}
  }
}
```

**同步执行 Proposal Agent + Word 渲染**(耗时 15–90s,前端建议超时 300s):

```
加载招标文件 + Requirement + 企业资料(knowledge_type='company')
  ↓
Proposal Agent(ReAct 循环,5 个无状态 Tool):
  - requirement_tool          读取 15 字段 Requirement
  - bid_knowledge_search_tool 复用 Sprint 4 retriever,按 knowledge_type 过滤
  - company_profile_tool      读取企业资料(资质 / 案例)
  - proposal_section_tool     调 LLM 生成章节内容(technical/commercial/...)
  - compliance_rule_tool      确定性规则校验(必填章节 / 关键字段)
  ↓
渲染 Word(docxtpl + python-docx,复用 Sprint 6)
  ↓
单事务落库 GeneratedProposal + ProposalSections
```

**响应**(200):

```json
{
  "code": 200,
  "message": "投标文件生成成功",
  "data": {
    "proposal": {
      "id": 1,
      "proposal_no": "PR-20260807013500-I9J0K1L2",
      "bid_document_id": 1,
      "status": "success",
      "generated_sections": [
        {"section_type": "technical", "section_name": "技术方案", "source": "ai", "references": [...]}
      ],
      "rag_references": [{"document_title": "...", "chunk_id": 1, "page_number": 2, "score": 0.89}],
      "validation_results": {"passed": true, "issues": []},
      "trace_summary": {"steps": 7, "total_duration_ms": 12450, "iterations": 3, "max_iterations": 5},
      "file_info": {"name": "投标文件.docx", "size": 102400},
      "iterations": 3
    }
  }
}
```

> Agent 失败(LLM 不可用)走兜底:仍渲染 Word(规则骨架,无 AI 章节),接口不报错,`llm_error` 字段记录原因。
> 招标文件需 `parse_status=success` 才能生成,否则返回 400。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 招标文件未解析成功 / Requirement 不存在 |
| 404 | 招标文件不存在 / employee 操作他人资源 |

### 12.9 投标生成记录列表

```
GET /api/v1/proposals
```

**权限**:JWT(admin / manager 全部;employee 仅自己触发的)

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| page | int | 1 | 页码 |
| size | int | 20 | 每页数量(最大 100) |
| status | string | - | 状态过滤(pending / running / success / failed) |
| bid_document_id | int | - | 招标文件过滤 |

**响应**(200):`data.items` 含生成记录列表(含招标文件摘要,不含 sections / trace)。

### 12.10 生成记录详情

```
GET /api/v1/proposals/{proposal_id}
```

**权限**:JWT(admin / manager 任意;employee 仅自己触发的,他人返回 404)

**响应**(200):返回 `data.proposal`,含 `generated_sections` / `rag_references` / `validation_results` / `agent_trace` / `trace_summary` / `file_info` / 招标文件摘要。

### 12.11 生成记录 Agent Trace

```
GET /api/v1/proposals/{proposal_id}/trace
```

**权限**:JWT(admin / manager 任意;employee 仅自己触发的)

**用途**:供前端 `ProposalDetail` 页 Agent 执行过程 Timeline 展示(Thought → Decision → Action → Observation → Duration → Status)。

**响应**(200):

```json
{
  "code": 200,
  "data": {
    "trace": {
      "id": 1,
      "proposal_no": "PR-20260807013500-I9J0K1L2",
      "status": "success",
      "iterations": 3,
      "agent_trace": [
        {
          "step": 1,
          "thought": "需先读取招标 Requirement...",
          "decision": "call_tool:requirement_tool",
          "action": "requirement_tool",
          "tool_input": {"bid_document_id": 1},
          "observation": {"project_name": "XX 项目", "...": "..."},
          "start_time": "2026-08-07 01:35:00",
          "end_time": "2026-08-07 01:35:01",
          "duration_ms": 1024,
          "status": "success",
          "error_message": null
        }
      ],
      "trace_summary": {
        "steps": 7,
        "total_duration_ms": 12450,
        "llm_duration_ms": 8200,
        "tool_duration_ms": 4250,
        "tool_stats": {"requirement_tool": {"calls": 1, "success": 1}},
        "llm_stats": {"calls": 3, "success": 3, "errors": 0},
        "iterations": 3,
        "max_iterations": 5,
        "iteration_exceeded": false
      },
      "llm_error": null,
      "llm_error_type": null
    }
  }
}
```

> Trace 结构与 Sprint 5/6 完全一致(12 字段/步),前端可复用 `GenerationDetail` 的 Timeline 组件。

### 12.12 下载投标文件

```
GET /api/v1/proposals/{proposal_id}/download
```

**权限**:JWT(admin / manager 任意;employee 仅自己触发的)

**流程**:校验存在 + 权限 → 校验 `status=success` → 校验文件物理存在 → 返回 Word 文件流。

**响应**:`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`,附件下载(`Content-Disposition: attachment`)。

**异常**:

| code | 触发场景 |
|------|---------|
| 400 | 生成记录 status != success / 文件丢失 |
| 404 | 生成记录不存在 / employee 下载他人文件 |

### 12.13 Bid Pipeline(招标解析流水线)

复用 Sprint 3 底层能力,不新建第二套 Pipeline:

```
招标文件(uploads/bids/{uuid}.ext)
  ↓
类型检测
  ├─ 文本 PDF → pdfplumber 文本提取(extract_text_from_pdf)
  └─ 图片/扫描 PDF → DeepSeek-VL OCR(extract_text_using_deepseek_ocr)
  ↓
文本清洗(clean_text:去噪 / 合并空白 / 去页眉页脚)
  ↓
Chunk 切分(SemanticChunker:长招标文档分块,overlap + metadata)
  ↓
LLM 抽取(DeepSeek + prompts/bid_requirement_v1.md)
  ↓
15 字段 Requirement JSON + 质量指标(confidence / missing_count)
  ↓
落库 BidRequirement(1:1 关联 BidDocument)
```

**质量指标**:
- `confidence`:LLM 自评各字段置信度均值(0–1)
- `missing_count`:null / 空数组字段数(共 15)
- `field_count`:已提取字段数(15 − missing_count)

### 12.14 Proposal Agent(投标方案生成 Agent)

手写 ReAct(不引入 LangGraph),沿用 Sprint 5/6 Agent 架构。LLM 负责决策,Tool 负责执行:

| Tool | 职责 | 是否调 LLM | 复用关系 |
|------|------|:----------:|----------|
| `requirement_tool` | 读取 15 字段 Requirement | ❌ | 上下文预加载 |
| `bid_knowledge_search_tool` | RAG 检索企业知识(按 knowledge_type 过滤) | ❌ | 复用 Sprint 4 retriever |
| `company_profile_tool` | 读取企业资料(资质 / 案例) | ❌ | 上下文预加载 |
| `proposal_section_tool` | 调 LLM 生成章节内容 | ✅ | DeepSeek + prompts/proposal_section_v1.md |
| `compliance_rule_tool` | 确定性规则校验(必填章节 / 关键字段) | ❌ | 镜像 Sprint 6 contract_rule_tool |

**Prompt 版本管理**(prompts/ 目录,不硬编码):
- `bid_requirement_v1.md`:15 字段抽取
- `bid_proposal_v1.md`:Proposal Agent ReAct 系统提示
- `proposal_section_v1.md`:章节内容生成

**兜底策略**:LLM 不可用 → `compliance_rule_tool` 生成规则骨架 → 仍渲染 Word(无 AI 章节),`llm_error_type` 记录错误分类(timeout / rate_limit / server_error / network)。

**MAX_ITERATIONS=5**:防止 ReAct 死循环,超限自动终止并兜底。

---

## 十三、错误码汇总

| code | 含义 | 触发示例 |
|------|------|---------|
| 200 | 成功 | 所有成功请求 |
| 400 | 参数/业务错误 | 注册参数非法、用户名重复、非法状态跳转、模板必填变量缺失、模板已有生成记录拒绝删除、招标文件未解析成功即生成投标 |
| 401 | 认证失败 | 登录密码错误、JWT 缺失/无效/过期 |
| 403 | 授权失败 | role_required 角色不符(employee 上传/启停/删除模板、employee 删除招标文件) |
| 404 | 资源不存在 | 路由不存在、用户/合同/模板/生成记录/招标文件不存在、employee 查询他人资源 |
| 405 | 方法不允许 | GET 访问 POST 接口 |
| 413 | 文件过大 | 上传超过 10MB |
| 500 | 服务器内部错误 | 未捕获异常、Word 渲染失败、建合同失败 |

---

## 十四、接口开发规范

所有新增接口必须:

1. 添加接口文档(更新本文档)
2. 添加参数说明
3. 添加返回示例
4. 添加权限说明
5. 添加异常情况

### 分层约束

```
Request
  ↓
API 层(api/*/routes.py)   参数接收 / 校验 / 返回统一 Response
  ↓
Service 层(services/*)     业务逻辑
  ↓
Model 层(models/*)         数据库映射
  ↓
Database
```

**禁止**:
- API 层直接访问数据库
- API 层直接生成 JWT
- API 层直接调用 OCR / LLM
- `return str(e)` / `print()`
- 硬编码 Prompt / Secret

---

## 十五、Prompt 管理模块 API(v1.0.0 Sprint 8 新增)

**路径**:`/api/v1/prompts`
**Blueprint**:`prompt_bp`
**权限角色**:admin / contract_manager (CRUD);employee 可读(GET 列表/详情)
**降级承诺**:DB active Prompt 加载失败 / 不存在 → 自动回退到 `prompts/*.md` → 兜底默认 Prompt;任何异常不阻断 Agent 主流程。

### 15.1 Prompt 覆盖范围(VALID_NAMES)

| name | 对应模块 | 原 .md 文件 |
|------|----------|-------------|
| `contract_review` | Sprint 5 合同审核 Agent | `backend/app/ai/agent/prompts/contract_review_v1.md` |
| `contract_generation` | Sprint 6 合同生成 Agent | `backend/app/ai/generation/prompts/contract_generation_v1.md` |
| `bid_proposal` | Sprint 7 投标方案 Agent | `backend/app/ai/bid/prompts/bid_proposal_v1.md` |
| `bid_requirement` | Sprint 7 招标需求抽取 | `backend/app/ai/bid/prompts/bid_requirement_v1.md` |
| `rag_answer` | Sprint 4 RAG 问答 | `backend/app/knowledge/prompts/rag_answer.md` |
| `contract_extract` | Sprint 3 合同字段抽取 | `backend/app/ai/pipeline/prompts/contract_extract_v1.md` |

### 15.2 状态机(draft / active / inactive)

- `draft`:草稿,未启用;load_prompt 不读取
- `active`:启用中;**同一 name 只能有 1 个 active**;activate 其他同 name 时自动把旧 active 置为 inactive
- `inactive`:已停用(被新版本顶替);load_prompt 不读取

### 15.3 获取 Prompt 列表

```
GET /api/v1/prompts
```

Query 参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | String | 否 | 按 name 过滤 |
| status | String | 否 | 按 status 过滤(draft/active/inactive) |
| page | Integer | 否 | 页码,默认 1 |
| size | Integer | 否 | 每页,默认 20 |

响应:

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "total": 3,
    "items": [
      {
        "id": 1,
        "name": "contract_review",
        "version": "v1.0",
        "description": "合同审核 v1.0",
        "status": "active",
        "created_by": 1,
        "created_by_username": "admin",
        "created_time": "2026-08-07 12:00:00",
        "updated_time": "2026-08-07 12:00:00"
      }
    ]
  }
}
```

### 15.4 获取 Prompt 详情

```
GET /api/v1/prompts/{id}
```

响应 `data`:

```json
{
  "id": 1,
  "name": "contract_review",
  "version": "v1.0",
  "system_prompt": "You are a senior contract attorney ...",
  "human_prompt": "Please review the following contract:\\n{{contract_text}}",
  "description": "合同审核 v1.0",
  "status": "active",
  "created_by": 1,
  "created_by_username": "admin",
  "created_time": "2026-08-07 12:00:00",
  "updated_time": "2026-08-07 12:00:00"
}
```

### 15.5 创建 Prompt

```
POST /api/v1/prompts
```

权限:admin / contract_manager

请求体:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | String | 是 | VALID_NAMES 之一 |
| version | String | 否 | 默认 v1.0,建议语义化 |
| system_prompt | String | 是 | 系统提示 |
| human_prompt | String | 是 | 人类提示(支持 `{{var}}` 占位) |
| description | String | 否 | 描述 |
| status | String | 否 | 默认 draft |

响应:`201 Created`,data = 新建的 Prompt 详情对象(含 id)。

异常:

- 400:`name` 非法或 `system_prompt/human_prompt` 为空
- 403:非 admin / contract_manager

### 15.6 更新 Prompt

```
PUT /api/v1/prompts/{id}
```

权限:admin / contract_manager

允许部分更新字段:`version / system_prompt / human_prompt / description / status`。

> 约束:`status` 只允许 PUT 为 draft / inactive;若需要激活请用 15.7 activate 专用接口(保证同名唯一)。

### 15.7 激活 Prompt(版本切换)

```
POST /api/v1/prompts/{id}/activate
```

权限:admin / contract_manager

逻辑:

1. 查询该 Prompt.name 下所有其他 status=active 的记录 → 统一 update 为 `inactive`
2. 把 {id} 这条 update 为 `status=active`
3. DB 事务内完成,任何回滚不影响

响应:`200 OK`,data = 更新后的 Prompt 详情。

### 15.8 删除 Prompt

```
DELETE /api/v1/prompts/{id}
```

权限:admin 仅。contract_manager 默认不可删除(避免误删历史版本)。

约束:若该 Prompt 状态为 active 且当前 name 无其他 draft/inactive 可替换 → 拒绝删除,返回 400(message="该版本为最后一个 active,请先 activate 其他版本再删除")。

---

## 十六、日志模块 API(v1.0.0 Sprint 8 新增)

**路径**:`/api/v1/logs`
**Blueprint**:`logs_bp`
**权限角色**:仅 admin。
**降级承诺**:日志写入失败(DB 异常)→ logger.warning + 不抛,绝不阻断业务接口返回。

### 16.1 AI 调用日志列表(ai_request_logs)

```
GET /api/v1/logs/ai
```

Query 参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_type | String | 否 | contract_review / generation / bid_proposal / rag / contract_extract |
| status | String | 否 | success / failed |
| user_id | Integer | 否 | 按用户过滤 |
| related_type | String | 否 | contract / generation / proposal / document / rag |
| related_id | Integer | 否 | 业务 ID |
| page | Integer | 否 | 1 |
| size | Integer | 否 | 20 |

响应 `data.items[*]`:

```json
{
  "id": 1,
  "user_id": 2,
  "username": "admin",
  "agent_type": "contract_review",
  "model": "deepseek-chat",
  "prompt_version": "db:contract_review:v1.0",
  "input_tokens": 4200,
  "output_tokens": 680,
  "total_tokens": 4880,
  "latency_ms": 5120,
  "status": "success",
  "error_message": null,
  "related_type": "review_report",
  "related_id": 17,
  "trace_summary": {"tool_call_count": 5, "tool_success_count": 5, "tool_failed_count": 0},
  "created_time": "2026-08-07 12:00:00"
}
```

### 16.2 AI 调用日志详情

```
GET /api/v1/logs/ai/{id}
```

返回单条 AIRequestLog 完整对象(含 `trace_summary` JSON)。

### 16.3 操作审计日志列表(operation_logs)

```
GET /api/v1/logs/operations
```

Query 参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| operation_type | String | 否 | user_login / contract_upload / contract_review / contract_generate_preview / contract_generate / knowledge_upload / knowledge_delete / bid_upload / bid_parse / bid_requirement_submit / bid_requirement_review / bid_generate / template_upload / template_delete |
| user_id | Integer | 否 | 用户过滤 |
| target_type | String | 否 | user / contract / review / generation / document / bid / proposal / template |
| status_code | Integer | 否 | HTTP 状态码 |
| page | Integer | 否 | 1 |
| size | Integer | 否 | 20 |

响应 `data.items[*]`:

```json
{
  "id": 1,
  "user_id": 2,
  "username": "admin",
  "operation_type": "contract_upload",
  "target_type": "contract",
  "target_id": 33,
  "http_method": "POST",
  "path": "/api/v1/contracts/upload",
  "status_code": 201,
  "duration_ms": 830,
  "ip": "192.168.1.20",
  "summary": "合同上传成功:采购合同.pdf",
  "error_message": null,
  "created_time": "2026-08-07 12:00:00"
}
```

### 16.4 操作审计日志详情

```
GET /api/v1/logs/operations/{id}
```

返回单条 OperationLog 完整对象。

---

## 十七、AI 评估模块 API(v1.0.0 Sprint 8 新增)

**路径**:`/api/v1/evaluation`
**Blueprint**:`evaluation_bp`
**权限角色**:仅 admin。

### 17.1 获取实时评估报告(内存返回)

```
GET /api/v1/evaluation/report
```

Query 参数:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| days | Integer | 否 | 统计最近 N 天,默认 30 |

响应 `data`:

```json
{
  "report_no": "EV-20260807-00001",
  "period_start": "2026-07-08 00:00:00",
  "period_end": "2026-08-07 23:59:59",
  "persisted": false,
  "generated_by": 1,
  "generated_by_username": "admin",
  "created_time": "2026-08-07 12:00:00",
  "summary": {
    "total_ai_requests": 142,
    "ai_success_rate": 0.958,
    "total_operations": 537,
    "operation_failure_rate": 0.039
  },
  "metrics": {
    "rag": {
      "call_count": 62,
      "success_count": 60,
      "success_rate": 0.968,
      "avg_latency_ms": 820,
      "p95_latency_ms": 1630,
      "avg_total_tokens": 2150
    },
    "agent": {
      "contract_review_success_rate": 0.94,
      "contract_generation_success_rate": 0.96,
      "bid_proposal_success_rate": 0.92,
      "review_total": 23,
      "generation_total": 18,
      "bid_total": 15
    },
    "tool": {
      "total_calls": 376,
      "success_count": 370,
      "failed_count": 6,
      "success_rate": 0.984,
      "tool_breakdown": [
        {"tool_name": "KnowledgeSearchTool", "calls": 87, "success": 86, "failed": 1, "success_rate": 0.989},
        {"tool_name": "ContractFieldTool", "calls": 23, "success": 23, "failed": 0, "success_rate": 1.0}
      ]
    },
    "cost": {
      "input_tokens": 312000,
      "output_tokens": 89000,
      "total_tokens": 401000
    },
    "operation": {
      "total_count": 537,
      "success_count": 516,
      "failed_count": 21,
      "failure_rate": 0.039
    }
  }
}
```

### 17.2 生成 + 持久化评估快照

```
POST /api/v1/evaluation/report
```

请求体(可选):

```json
{"days": 30}
```

逻辑:同 17.1 计算 → `INSERT evaluation_reports`(metrics + summary JSON 落库)→ 返回完整对象(`persisted=true`,含 `id`)。

响应:`201 Created`,data = 同上,额外含 `"id": <整数主键>`。

### 17.3 历史评估报告列表

```
GET /api/v1/evaluation/reports
```

Query 参数:`page` / `size`。返回 `{total, items[{id, report_no, period_start, period_end, generated_by, created_time}]}`。

### 17.4 历史评估报告详情

```
GET /api/v1/evaluation/reports/{id}
```

返回 id 对应的完整评估报告对象(含 metrics + summary JSON)。

---

## 十八、Sprint 8 总结与兼容性

### 18.1 新增 API 汇总(共 21 个端点)

| 模块 | Blueprint | 端点 | 数量 |
|------|-----------|------|------|
| Prompt 管理 | prompt_bp | GET/POST /prompts · GET/PUT /prompts/{id} · POST /prompts/{id}/activate · DELETE /prompts/{id} | 6 |
| AI 日志 | logs_bp | GET /logs/ai · GET /logs/ai/{id} | 2 |
| 操作审计 | logs_bp | GET /logs/operations · GET /logs/operations/{id} | 2 |
| AI 评估 | evaluation_bp | GET/POST /evaluation/report · GET /evaluation/reports · GET /evaluation/reports/{id} | 4 |
| 合计 | — | — | 14(仅 REST 公开端点;不含 RAG Cache / AI Log / Audit 中间件内部 hooks) |

> 注:Redis Cache / AI Log / Audit 的业务钩子均为 Service 层内部函数,不计入独立 REST API。Sprint 8 总计公开 14 个新 REST 端点。

### 18.2 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_URL` | `''`(空=不启用 Redis) | `redis://user:pass@host:6379/0` 格式 |
| `CACHE_ENABLED` | `True` | False = 强制全部走内存降级 |
| `CACHE_TTL_RAG` | `3600`(秒) | RAG 查询缓存 TTL |
| `CACHE_TTL_REVIEW` | `1800`(秒) | 审核结果缓存 TTL |
| `CACHE_TTL_GEN` | `1800`(秒) | 生成结果缓存 TTL |

### 18.3 降级链全景

```
用户请求
  │
  ├─► CacheService
  │      Redis 可用 ──────► Redis
  │      Redis 异常 ──────► _MemoryFallback(内存 LRU)
  │      两者都异常 ─────► 跳过缓存,继续业务(不抛)
  │
  ├─► PromptService.load_prompt(name)
  │      DB active 存在且读取成功 ─────► DB Prompt
  │      DB 失败 / 不存在 ─────────────► 原 prompts/*.md 文件
  │      文件也失败 ───────────────────► 兜底默认 Prompt(不会抛)
  │
  ├─► AI 日志 / 审计中间件
  │      写入 DB 成功 ─────► 持久化
  │      写入 DB 失败 ─────► logger.warning,不影响原响应
  │
  └─► Evaluation Service
         聚合表失败(空表 / 异常)────► 返回空指标({count=0, rate=0})
```

### 18.4 RBAC 矩阵(v1.0.0 新增部分)

| 功能 | admin | contract_manager | employee |
|------|:-----:|:----------------:|:--------:|
| Prompt CRUD(列表/详情) | √ | √ | √(只读) |
| Prompt 创建/更新/激活 | √ | √ | × |
| Prompt 删除 | √ | × | × |
| AI 日志查询 | √ | × | × |
| 操作审计查询 | √ | × | × |
| AI 评估生成/查询 | √ | × | × |
| (Sprint 0~7 原有接口) | 不变 | 不变 | 不变 |
