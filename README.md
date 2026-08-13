# 智能合同与投标管理平台

> 基于 Flask + LangChain + DeepSeek + RAG + ReAct Agent 构建的企业级 AI 合同与投标智能管理平台。

## 项目简介

智能合同与投标管理平台是一套面向企业场景的 AI 应用系统，提供合同生命周期管理、智能文档解析、企业知识库检索增强生成（RAG）、合同风险审核 Agent、AI 合同生成以及投标方案自动生成等能力。

项目采用企业级后端架构设计，通过 Pipeline、Agent、Knowledge Layer 等模块实现 AI 能力与业务系统解耦。

---

# 核心能力

## 1. 合同生命周期管理

支持企业合同完整业务流程：

* 合同上传与管理
* 合同列表与权限控制
* 合同状态流转
* 合同详情查看
* AI分析结果管理

支持角色：

* Admin
* Contract Manager
* Employee

---

## 2. 企业级文档 AI Pipeline

针对合同、招标文件等企业文档构建自动化处理流程：

```
Document
   ↓
Extract
   ↓
OCR
   ↓
Clean
   ↓
Chunk
   ↓
LLM Analysis
   ↓
Database
```

主要能力：

* PDF文本解析
* 图片OCR识别
* 文档清洗
* 智能分块
* LLM结构化字段提取
* 分析任务追踪

---

## 3. 企业知识库 RAG

构建企业级知识增强系统：

技术方案：

* FAISS向量数据库
* BGE中文Embedding模型
* Retriever检索
* DeepSeek生成

支持：

* 企业知识上传
* 文档向量化
* 相似度检索
* 引用来源返回
* RAG问答

---

## 4. AI合同审核 Agent

基于手写 ReAct Agent 实现智能合同风险审核：

流程：

```
用户请求
   ↓
Agent决策
   ↓
Tool调用
   ↓
结果观察
   ↓
生成审核报告
```

Agent工具：

* 合同字段查询
* 企业知识检索
* 风险规则检查

支持：

* 风险识别
* 风险等级评估
* 审核报告生成
* Agent执行轨迹记录

---

## 5. AI合同自动生成

实现：

```
模板
 ↓
变量填写
 ↓
RAG知识检索
 ↓
AI条款生成
 ↓
规则校验
 ↓
Word生成
```

能力：

* Word模板管理
* 自动变量解析
* AI补充合同条款
* 自动生成DOCX文件
* 生成记录追踪

---

## 6. AI投标方案生成

支持企业投标场景：

流程：

```
招标文件
 ↓
需求解析
 ↓
企业知识检索
 ↓
Proposal Agent
 ↓
投标方案生成
 ↓
Word输出
```

能力：

* 招标文件解析
* 投标需求提取
* 企业资料匹配
* 技术方案生成
* 商务方案生成

---

# 系统架构

```
                 Frontend
             Vue3 + Element Plus
                     |
                     |
                 API Layer
          Flask Blueprint Routes
                     |
                     |
              Service Layer
        Business Logic Orchestration
                     |
        -----------------------------
        |             |             |
     Pipeline       Agent       Knowledge
        |             |             |
 Document Flow   ReAct Agent      RAG
                     |
                     |
              AI Service Layer
          DeepSeek / Embedding
                     |
                     |
                Database
          SQLite / MySQL
```

---

# 技术栈

## Backend

* Flask
* Flask-SQLAlchemy
* Flask-JWT-Extended
* LangChain
* Python

## AI

* DeepSeek API
* ReAct Agent
* RAG
* FAISS
* Sentence Transformers

## Document Processing

* pdfplumber
* OCR
* docxtpl
* python-docx

## Frontend

* Vue3
* Vite
* Element Plus
* Pinia
* Axios

---

# 项目结构

```
backend
├── app
│   ├── api              # API接口
│   ├── services         # 业务服务
│   ├── ai               # AI能力
│   │   ├── pipeline     # 文档Pipeline
│   │   ├── agent        # Agent系统
│   │   └── bid          # 投标Agent
│   ├── knowledge        # RAG知识库
│   ├── models           # 数据模型
│   └── extensions       # 基础设施


frontend
├── src
│   ├── pages
│   ├── components
│   ├── api
│   └── store


docs
├── API_DESIGN.md
├── DATABASE_DESIGN.md
├── SPRINT_REPORT.md
└── CHANGELOG.md
```

---

# 快速开始

## 后端

```bash
cd backend

pip install -r requirements.txt

cp .env.example .env

python run.py
```

默认：

```
http://127.0.0.1:5001
```

---

## 前端

```bash
cd frontend

npm install

npm run dev
```

默认：

```
http://localhost:5173
```

---

# 环境配置

主要配置：

```env
DEEPSEEK_API_KEY=your_key

DATABASE_URL=sqlite:///instance/app.db

EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

---

# 项目特点

相比传统 CRUD 系统，本项目重点探索企业 AI 应用工程化：

* Pipeline 模块化设计
* RAG知识增强
* ReAct Agent工具调用
* Agent Trace可观测
* AI任务状态追踪
* Prompt版本管理
* AI效果评估体系

---

# 文档

详细设计文档：

```
docs/

├── API_DESIGN.md
├── DATABASE_DESIGN.md
├── FRONTEND_ARCHITECTURE.md
├── CHANGELOG.md
└── SPRINT_REPORT.md
```

---

# Roadmap

已完成：

* [x] 合同管理系统
* [x] AI文档解析Pipeline
* [x] 企业知识库RAG
* [x] 合同审核Agent
* [x] AI合同生成
* [x] AI投标方案生成
* [x] Agent Trace
* [x] AI评估体系

未来规划：

* [ ] Docker部署
* [ ] MinIO对象存储
* [ ] Redis任务队列
* [ ] Celery异步任务
* [ ] 企业级权限体系增强

---

# License

MIT License
