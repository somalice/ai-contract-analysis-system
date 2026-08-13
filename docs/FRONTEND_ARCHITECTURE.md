# 前端架构设计文档(Admin Console)

> **版本**:v0.4.0(Sprint 2 - Phase A + Phase B)
> **创建日期**:2026-08-05
> **定位**:基于 Vue3 + Element Plus 从零构建的企业级后台管理系统(Progressive Admin Design)

---

## 一、设计原则

### 1.1 Progressive Admin Design(渐进式后台)

- **只开发当前 Sprint 已实现的业务页面**
- **禁止**提前创建未来 Sprint 菜单 / 空白页面 / 占位页面
- **禁止**引入任何第三方后台模板(vue-element-admin / Ant Design Pro / 若依等)
- 每个 Sidebar 菜单项必须对应一个已完成的业务模块
- 随 Sprint 推进逐步扩展菜单与页面

### 1.2 职责单一

- `api/` 仅封装 HTTP 请求,不处理业务
- `store/` 仅管理认证态(JWT / 用户 / 登录状态),不放业务数据
- `router/` 仅定义路由表与守卫,不写业务逻辑
- `pages/` 负责页面 UI 与交互编排,通过 api 模块调后端
- `components/` 仅承载可复用 UI 组件,无业务耦合
- `utils/` 提供纯函数工具(常量 / 格式化)

### 1.3 前后端完全分离

- 前端独立部署在 5173 端口(Vite dev server)
- 后端 Flask 仅暴露 `/api/*` JSON 接口
- 跨域由后端 Flask-CORS 精确控制(仅 `/api/*`,Origin 白名单预留 .env)
- 前端不依赖后端模板渲染,纯 SPA

---

## 二、技术栈

| 模块 | 技术 | 版本 |
|------|------|------|
| 框架 | Vue 3 | ^3.4.21 |
| 构建工具 | Vite | ^5.2.0 |
| UI 库 | Element Plus | ^2.7.0 |
| UI 图标 | @element-plus/icons-vue | ^2.3.1 |
| 路由 | Vue Router | ^4.3.0 |
| 状态管理 | Pinia | ^2.1.7 |
| HTTP 客户端 | Axios | ^1.7.2 |
| 语言 | JavaScript(**不用 TypeScript**,本阶段约束) |

---

## 三、目录结构

```
frontend/
├── .gitignore                    # 忽略 node_modules/ dist/ .env.local
├── .env.development              # VITE_API_BASE_URL=http://127.0.0.1:5001/api/v1
├── .env.production               # VITE_API_BASE_URL=/api/v1(同源部署)
├── index.html                    # HTML 入口
├── package.json                  # 依赖与脚本(dev/build/preview)
├── vite.config.js                # Vite 配置(端口 5173,alias @ → src)
└── src/
    ├── main.js                   # 应用入口(注册 Vue/Element Plus/Pinia/Router/全局图标)
    ├── App.vue                   # 根组件(<router-view/>)
    ├── api/
    │   ├── request.js            # Axios 封装(BaseURL/JWT/异常/401 跳登录)
    │   ├── auth.js               # 认证 API(login/profile/register)
    │   └── contract.js           # 合同 API(upload/list/detail/updateStatus)
    ├── assets/                   # 静态资源(预留)
    ├── components/
    │   ├── SidebarMenu.vue       # 侧边栏菜单(根据路由高亮)
    │   └── contract/
    │       └── StatusTag.vue     # 合同状态标签(主状态 + AI 分析状态)
    ├── layouts/
    │   └── AdminLayout.vue       # 后台布局(Header + Sidebar + Main)
    ├── pages/
    │   ├── Login.vue             # 登录页
    │   ├── Dashboard.vue         # 仪表盘(欢迎 + 快捷入口 + 系统信息)
    │   ├── NotFound.vue          # 404 页
    │   └── contract/
    │       ├── ContractList.vue   # 合同列表(分页/搜索/状态过滤)
    │       ├── ContractUpload.vue # 上传合同(PDF + AI 分析)
    │       └── ContractDetail.vue # 合同详情(信息/AI 结果/状态流转)
    ├── router/
    │   └── index.js              # 路由表 + 全局守卫(JWT 校验 + 角色控制)
    ├── store/
    │   └── auth.js               # Pinia 认证 store(token/user/login/getters)
    ├── styles/
    │   └── index.css             # 全局样式重置 + 公共类
    └── utils/
        ├── constants.js          # 角色/状态枚举/状态机/标签映射/版本
        └── format.js             # formatFileSize/formatTime/truncate
```

---

## 四、分层关系

```
                    用户浏览器(5173)
                          │
                ┌─────────▼─────────┐
                │   main.js 入口    │  注册 Vue + Element Plus + Pinia + Router
                └─────────┬─────────┘
                          │
                ┌─────────▼─────────┐
                │   router 守卫     │  JWT 校验 + 角色控制 + 标题设置
                └─────────┬─────────┘
                          │
                ┌─────────▼─────────┐
                │   AdminLayout     │  Header + SidebarMenu + <router-view/>
                └─────────┬─────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌─────▼─────┐     ┌────▼────┐
   │ Login   │      │ Dashboard │     │ Contract│
   └────┬────┘      └─────┬─────┘     │  Pages  │
        │                 │           └────┬────┘
        │           ┌─────▼─────┐          │
        │           │ authStore │ ◄────────┤  状态共享(token/user)
        │           └─────┬─────┘          │
        │                 │                │
        └────────┬────────┴────────────────┘
                 │
          ┌──────▼──────┐
          │  api/*.js   │  统一封装 Axios(注入 JWT/异常处理)
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │  request.js │  Axios 实例(BaseURL + 拦截器)
          └──────┬──────┘
                 │
                 ▼  HTTP + JSON(JWT Bearer)
        后端 Flask /api/v1/*(5001)
```

### 关键数据流

1. **登录**:Login.vue → `authStore.login()` → `authApi.login()` → 后端 `/auth/login` → 返回 access_token + user → 存入 Pinia + localStorage → 跳转 Dashboard
2. **刷新页面**:router 守卫检测 `isLoggedIn && !user` → `authStore.fetchProfile()` → 后端 `/auth/profile` → 恢复用户信息
3. **业务请求**:页面调 `api/contract.js` → `request.js` 拦截器注入 `Authorization: Bearer {token}` → 后端 → 响应拦截器统一处理 `{code,message,data}`
4. **401 处理**:响应拦截器检测 `code===401` 或 HTTP 401 → 清除 localStorage → ElMessage 提示 → 1s 后跳转 `/login`
5. **状态流转**:ContractDetail.vue → `updateContractStatus(id, target)` → 后端 PATCH → 状态机校验 → 返回新合同对象 → 更新本地 state

---

## 五、Layout 设计

### AdminLayout.vue(Header + Sidebar + Main)

```
┌──────────────────────────────────────────────────────────┐
│ Header(60px)                                            │
│  [Logo] 智能合同与投标管理平台 [v0.4.0]   [admin 管理员 ▾] │
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  Sidebar   │              Main(<router-view/>)           │
│  (220px)   │                                             │
│            │                                             │
│  仪表盘    │                                             │
│  合同管理  │                                             │
│  上传合同  │                                             │
│            │                                             │
└────────────┴─────────────────────────────────────────────┘
```

- **Header**:系统名称 + 版本标签 + 用户下拉(我的账户 / 退出登录)
- **Sidebar**:el-menu(router 模式,根据当前路由自动高亮)
- **Main**:el-main 包裹 `<router-view/>`,带内边距与滚动

### SidebarMenu.vue

- 当前菜单项(Progressive):仪表盘 / 合同管理 / 上传合同
- 合同详情页(`/contracts/:id`)高亮"合同管理"父菜单
- 所有角色均可见这三项(权限差异在后端与详情页按钮层级体现)
- 后续 Sprint 增加新菜单时,直接在此组件追加 `<el-menu-item>`

---

## 六、Router 设计

### 路由表

| 路径 | 名称 | 组件 | 认证 | 说明 |
|------|------|------|------|------|
| `/login` | Login | Login.vue | 否 | 登录页(已登录访问自动跳 dashboard) |
| `/` | — | AdminLayout | 是 | 布局容器(redirect → /dashboard) |
| `/dashboard` | Dashboard | Dashboard.vue | 是 | 仪表盘 |
| `/contracts` | ContractList | ContractList.vue | 是 | 合同列表 |
| `/contracts/upload` | ContractUpload | ContractUpload.vue | 是 | 上传合同 |
| `/contracts/:id` | ContractDetail | ContractDetail.vue | 是 | 合同详情 |
| `/profile` | Profile | Profile.vue | 是 | 我的账户(RC 新增) |
| `/:pathMatch(.*)*` | NotFound | NotFound.vue | 否 | 404 |

### 全局前置守卫(beforeEach)

```javascript
1. 设置 document.title = `${to.meta.title} - 智能合同与投标管理平台`
2. 取 authStore
3. if (to.meta.requiresAuth === false):
     - if (to.name === 'Login' && isLoggedIn) → 跳 /dashboard
     - else → next()
4. if (!isLoggedIn) → 跳 /login?redirect=to.fullPath
5. if (isLoggedIn && !user) → await fetchProfile()(失败则 logout + 跳登录)
6. next()
```

**设计要点**:
- 前端仅控菜单/路由可达性,真正权限校验在后端
- 401 由 Axios 拦截器统一处理,守卫不重复处理
- 角色不符的路由暂未在前端拦截(后端已防枚举,前端按钮层级控制即可)

---

## 七、Store 设计(Pinia)

### auth.js(仅认证态)

| 类型 | 名称 | 说明 |
|------|------|------|
| state | `token` | JWT access_token(localStorage 持久化) |
| state | `user` | 当前用户对象 `{id, username, role, ...}` |
| getter | `isLoggedIn` | `!!token` |
| getter | `role` | `user?.role` |
| getter | `username` | `user?.username` |
| getter | `isAdmin` | `role === 'admin'` |
| getter | `isManager` | `role === 'admin' \|\| role === 'contract_manager'` |
| action | `login(credentials)` | 调 loginApi → 存 token + user |
| action | `fetchProfile()` | 调 getProfile → 刷新 user(用于页面刷新恢复) |
| action | `logout()` | 清空 state + localStorage |

**约束**:
- **不放业务数据**(合同列表 / 详情等由各页面自行管理)
- token 持久化到 `localStorage`,键名 `admin_token` / `admin_user`
- 页面刷新后通过 `fetchProfile()` 恢复用户信息

---

## 八、API 封装设计

### request.js(Axios 实例)

| 配置 | 值 | 说明 |
|------|------|------|
| baseURL | `import.meta.env.VITE_API_BASE_URL` | dev: `http://127.0.0.1:5001/api/v1` |
| timeout | 60000ms | 默认 60s(合同上传单独放宽到 180s) |

**请求拦截器**:
- 从 localStorage 读取 token,自动注入 `Authorization: Bearer {token}`

**响应拦截器**:
- `res.data.code === 200` → 返回 `res.data`
- `res.data.code === 401` → 清除 token/user + ElMessage + 1s 后跳 `/login`
- 其他 code → ElMessage.error(message) + reject
- HTTP 错误层(401/403/404/5xx / 超时 / 网络错误)→ 统一 ElMessage 提示

**约束**:
- **页面禁止重复写 Axios**,统一走 `api/*.js`
- Loading 由各页面按需控制(不在封装层强制)

### 业务 API 模块

| 模块 | 函数 | 后端接口 |
|------|------|---------|
| `api/auth.js` | `login(credentials)` | POST /auth/login |
| `api/auth.js` | `getProfile()` | GET /auth/profile |
| `api/auth.js` | `register(data)` | POST /auth/register |
| `api/contract.js` | `uploadContract(formData)` | POST /contracts/upload |
| `api/contract.js` | `listContracts(params)` | GET /contracts |
| `api/contract.js` | `getContractDetail(id)` | GET /contracts/{id} |
| `api/contract.js` | `updateContractStatus(id, status)` | PATCH /contracts/{id}/status |

---

## 九、页面设计

### 9.1 Login.vue

- Element Plus 表单:用户名 + 密码
- 表单校验(required + blur)
- 回车提交
- 调用 `authStore.login()`,成功跳转 `redirect` 参数指定的页面(默认 `/dashboard`)
- 失败由 Axios 拦截器统一提示
- 版本号 + 副标题

### 9.2 Dashboard.vue

- 欢迎卡片:用户名 + 角色 + 系统版本
- 快捷入口卡片:合同管理 / 上传合同 / 我的账户(点击跳转)
- 系统信息:el-descriptions 展示系统名称 / 版本 / 当前用户 / 角色 / 技术栈
- **不实现统计图表**(Progressive Admin Design)

### 9.3 ContractList.vue

- 筛选栏:关键字输入 + 状态下拉 + 搜索按钮 + 重置按钮
- 表格列:合同编号 / 标题 / 类型 / 状态(StatusTag) / 创建人 / 创建时间 / 操作(查看详情)
- 分页:el-pagination(支持 10/20/50/100 每页)
- 调用 `listContracts(params)` 真实接口
- 点击"查看详情"跳 `/contracts/:id`
- 空状态动态文案:有筛选条件时提示"未找到匹配的合同",无筛选时提示"暂无合同数据"(RC 优化)
- **权限**:employee 由后端隔离(仅返回自己合同),前端无需特殊处理

### 9.4 ContractUpload.vue

- 拖拽上传区(el-upload drag,accept=.pdf,.png,.jpg,.jpeg)
- 表单:合同类型 / 合同标题 / 描述(均可选)
- 前端校验:类型 + 大小(<=10MB)
- 调用 `uploadContract(formData)` 真实接口
- 上传中显示 Loading,按钮禁用
- 成功 → ElMessage.success + 跳转合同详情页
- 失败 → Axios 拦截器统一提示(保留表单允许重试)
- **AI 分析**:上传会真实触发 DeepSeek(复用 Sprint 0),可能耗时 10-30s

### 9.5 ContractDetail.vue

- 顶部操作栏:返回按钮 + 当前状态标签
- 基本信息卡片:合同编号 / 标题 / 类型 / 状态 / 描述
- 文件信息卡片:文件名 / 大小
- 创建人卡片:用户名 / 角色 / 创建时间 / 更新时间
- AI 分析结果卡片:
  - 分析中:Loading + 提示
  - 失败:warning alert
  - 完成:el-descriptions 展示合同名称 / 甲方 / 乙方 / 金额 / 签署日期
- 状态流转卡片(**仅 admin / contract_manager 可见**):
  - 显示当前状态 + 可流转目标按钮(基于 `STATUS_TRANSITIONS`)
  - 终态(archived)显示"终态,不可流转"
  - 点击流转 → ElMessageBox 确认 → 调 `updateContractStatus` → 刷新
  - **employee 隐藏整张卡片**(`canUpdateStatus` computed)

### 9.6 Profile.vue(RC 新增)

- 用户基本信息卡片:用户ID / 用户名 / 角色(tag) / 状态 / 注册时间 / 最后更新
- Token 信息卡片:Token 类型(Bearer JWT) / Token 前缀(仅前 20 字符,不暴露完整 Token) / 有效期
- 账户操作卡片:退出登录按钮(ElMessageBox 确认 → authStore.logout → 跳 /login)
- 数据来源:`authStore.user`(登录时获取,刷新页面时 `fetchProfile` 恢复)
- **约束**:不新增修改密码 / 头像上传等未来 Sprint 功能

---

## 十、权限控制设计

### 10.1 前端权限(仅控展示)

| 角色 | 菜单可见 | 状态流转按钮 | 数据范围 |
|------|---------|------------|---------|
| admin | 全部 | 显示 | 后端返回全部 |
| contract_manager | 全部 | 显示 | 后端返回全部 |
| employee | 全部 | **隐藏** | 后端仅返回自己 |

**实现**:
- 菜单:所有角色一致(Progressive,不区分菜单)
- 状态按钮:`canUpdateStatus = isAdmin || isManager`(ContractDetail.vue)
- 数据范围:后端 Service 层强制过滤(employee 仅 `creator_id == 自己`)

### 10.2 后端权限(真正校验)

- JWT 校验:`@jwt_required()` 拦截未登录
- 角色校验:`@role_required('admin','contract_manager')` 拦截 employee 状态更新
- 数据隔离:Service 层 `creator_id` 过滤
- 防枚举:employee 访问他人合同返回 404(非 403,不泄露存在性)
- 状态机:`is_valid_transition()` 拦截非法跳转

---

## 十一、与后端的契约

### 11.1 统一响应格式

```json
{ "code": 200, "message": "success", "data": {...} }
```

- 前端 Axios 拦截器根据 `code` 判断成功/失败
- 401 → 自动跳登录
- 其他非 200 → ElMessage 提示

### 11.2 合同对象结构

```json
{
  "id": 1,
  "contract_no": "CT-20260805113045-BA926C11",
  "title": "采购合同",
  "contract_type": "采购合同",
  "description": "...",
  "status": "draft",
  "file_info": { "name": "test.pdf", "size": 1405 },
  "analysis_status": "completed",
  "analysis_result": {
    "contract_name": "...",
    "party_a": "...",
    "party_b": "...",
    "amount": "...",
    "signing_date": "..."
  },
  "creator": { "id": 2, "username": "admin", "role": "admin", ... },
  "creator_id": 2,
  "created_time": "2026-08-05 11:30:45",
  "updated_time": "2026-08-05 11:30:51"
}
```

- **不暴露 `file_path`**(内部路径)
- `file_info` 仅含 name + size
- `analysis_result` 仅在详情接口返回(列表接口 `include_analysis=False`)

### 11.3 状态机契约

| 当前 \ 目标 | draft | reviewed | archived |
|------------|:-----:|:--------:|:--------:|
| **draft** | 禁止 | ✅ | 禁止 |
| **reviewed** | 禁止 | 禁止 | ✅ |
| **archived** | 禁止 | 禁止 | 禁止(终态) |

前端 `STATUS_TRANSITIONS` 常量与后端 `Contract.STATUS_TRANSITIONS` 完全一致,前端只提供合法选项,非法跳转由后端兜底拦截。

---

## 十二、后续 Sprint 扩展规划

### Sprint 3(AI 合同解析 Pipeline)

- **新增页面**:`/contracts/:id/analysis` AI 解析详情(中间步骤可视化)
- **菜单**:合同管理下新增子菜单(可选)
- **组件**:AnalysisPipeline.vue(展示 文本提取 → OCR → 清洗 → Chunk → LLM 流程)
- **状态扩展**:支持 `analyzing` / `approved` 状态(前端 STATUS_LABELS 扩展)

### Sprint 4+(RAG / Agent / 投标)

- **知识库管理**:`/knowledge` 知识文档上传 + 搜索
- **审核 Agent**:`/agents/audit` 合同风险分析报告
- **合同生成**:`/templates` 模板中心 + 生成
- **投标管理**:`/bids` 招标文件分析 + 投标文件生成

### 扩展原则

- 每个新 Sprint 完成业务模块后,再在 SidebarMenu 增加对应菜单
- 路由表追加新路由,组件按页面拆分
- 新增 API 模块按业务域拆分(`api/knowledge.js` / `api/agent.js` / `api/bid.js`)
- Store 仍只管认证态,业务数据由各页面自行管理
- 公共组件下沉到 `components/`(如 `components/knowledge/`、`components/agent/`)

---

## 十三、构建与部署

### 开发环境

```bash
cd frontend
npm install
npm run dev   # 启动 Vite dev server,端口 5173
```

### 生产构建

```bash
cd frontend
npm run build   # 输出到 dist/
npm run preview # 本地预览生产构建
```

### 环境变量

| 文件 | 变量 | 值 |
|------|------|------|
| `.env.development` | `VITE_API_BASE_URL` | `http://127.0.0.1:5001/api/v1` |
| `.env.production` | `VITE_API_BASE_URL` | `/api/v1`(同源部署,由 Nginx 反代) |

### 与后端的 CORS 配合

后端 `backend/.env` 的 `CORS_ORIGINS` 必须包含前端实际访问的 Origin:

```
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

仅对 `/api/*` 开放,不用 `*`,符合企业级安全要求。
