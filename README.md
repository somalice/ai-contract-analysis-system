# 📄 智能合同分析系统

基于 Flask + LangChain + DeepSeek AI 的智能合同管理系统，支持 PDF 解析和图片 OCR 识别。

## 🚀 技术栈

| 模块 | 技术 |
|------|------|
| **后端框架** | Flask |
| **PDF 解析** | pdfplumber |
| **图片处理** | Pillow |
| **OCR 识别** | DeepSeek Vision API |
| **AI 框架** | LangChain |
| **大模型** | DeepSeek Chat API |
| **前端样式** | Bootstrap 5 |

## ✨ 主要功能

### 📄 PDF 文件解析
- 使用 pdfplumber 提取有文字层的 PDF 内容
- 自动清理文本格式
- 支持大文件处理

### 🖼️ 图片 OCR 识别
- 支持 PNG、JPG、JPEG 格式图片
- 使用 DeepSeek Vision API 进行 OCR
- 扫描件识别准确率高

### 🤖 AI 合同字段提取
- 智能识别合同关键字段
- 自动提取合同名称、甲方、乙方
- 提取合同金额和签署日期
- 结构化输出 JSON 格式

## 🔄 处理流程

### PDF 处理流程
```
PDF 文件
    ↓
pdfplumber 文本提取
    ↓
文本清理优化
    ↓
LangChain + DeepSeek AI 分析
    ↓
提取合同字段
    ↓
展示 JSON 结果
```

### 图片 OCR 处理流程
```
PNG/JPG/JPEG 图片
    ↓
Base64 编码
    ↓
DeepSeek Vision API OCR
    ↓
获取识别文本
    ↓
LangChain + DeepSeek AI 分析
    ↓
提取合同字段
    ↓
展示 JSON 结果
```

## 📦 安装方法

### 1. 克隆项目
```bash
git clone <your-repo-url>
cd <project-directory>
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置 API Key
复制 `.env.example` 为 `.env` 并填写你的 DeepSeek API Key：
```bash
cp .env.example .env
```
然后编辑 `.env` 文件：
```
DEEPSEEK_API_KEY=your_api_key_here
```

### 4. 创建必要目录
```bash
mkdir uploads
```

## 🚀 启动方法

### Windows
```bash
python app.py
```

### macOS / Linux
```bash
python3 app.py
```

访问地址：http://127.0.0.1:5001/

## 📁 项目结构

```
smart-contract-analysis/
├── app.py                 # Flask 主应用
├── requirements.txt       # 项目依赖
├── README.md             # 项目说明
├── .gitignore            # Git 忽略配置
├── templates/
│   └── index.html        # 前端页面
├── uploads/              # 上传文件目录
└── static/               # 静态资源（如需要）
```

## 🎯 使用说明

1. 打开浏览器访问 http://127.0.0.1:5001/
2. 选择 PDF 或图片文件上传
3. 系统自动识别并提取合同字段
4. 查看提取结果和 JSON 数据

## 📋 支持的文件格式

| 格式 | 说明 | 处理方式 |
|------|------|---------|
| **PDF** | 有文字层的 PDF | pdfplumber 解析 |
| **PNG** | 图片格式 | DeepSeek OCR |
| **JPG** | 图片格式 | DeepSeek OCR |
| **JPEG** | 图片格式 | DeepSeek OCR |

## 🎨 页面预览

- 响应式设计，支持移动端
- Bootstrap 5 精美界面
- 文件上传进度提示
- OCR/AI 识别状态显示
- 识别模式标识（pdfplumber / DeepSeek OCR）
- JSON 数据格式化展示

## ⚠️ 注意事项

- 请确保 DeepSeek API Key 配置正确
- 扫描件 PDF 建议转为图片后上传
- 大文件上传可能需要调整 `MAX_CONTENT_LENGTH`
- OCR 速度取决于 API 响应时间

## 📝 TODO

- [ ] 添加更多文件格式支持
- [ ] 批量处理功能
- [ ] 历史记录存储
- [ ] 结果导出功能（Excel/Word）
- [ ] 更多合同类型支持

## 📄 License

MIT License

---

**感谢使用！如有问题请提交 Issue。**
