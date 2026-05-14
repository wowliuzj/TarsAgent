# Tars Agent

Tars Agent 是一个基于 Python 构建的最小化可行性 (MVP) AI 智能体。它旨在通过简单的 CLI 界面接收指令，并在受控的 Docker 环境中执行任务。

## 核心特性

- **单 Agent 架构**: 专注核心的 ReAct (Reasoning and Acting) 循环。
- **CLI 交互**: 快速、简洁的命令行输入与反馈。
- **持久化记忆**: 使用 PostgreSQL + PGVector 存储对话日志和向量数据。
- **工具调用**: 支持执行 Shell 命令、文件读写等任务。
- **模型灵活**: 通过 LiteLLM 支持 Gemini, Gemma, GPT 等多种模型。
- **隔离安全**: 默认在 Docker 容器中运行，限制工作空间在 `data/` 目录。

## 快速开始

### 1. 环境准备
确保已安装：
- Docker & Docker Compose
- Python 3.10+ (用于本地开发调试)

### 2. 配置环境变量
在项目根目录创建 `.env` 文件：
```env
GOOGLE_API_KEY=your_google_ai_studio_api_key
MODEL_NAME=gemini/gemini-1.5-flash
DATABASE_URL=postgresql://tars:tars_pass@db:5432/tars_db
```

### 3. 启动项目
```bash
docker-compose up -d
```

### 4. 运行 Agent
```bash
docker-compose run app python main.py "帮我检查 data 目录下的文件结构"
```

## 文档
- [SOUL.md](./SOUL.md): Agent 的核心准则与性格定义。
- [Architecture](./architecture.md): 详细的设计说明 (待完善)。
