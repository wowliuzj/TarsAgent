# Tars Agent

Tars Agent 是一个基于 Python 构建的高性能模块化 AI 智能体。它采用分层架构（Tiered Capability），具备强大的逻辑推理能力、动态扩展的技能库以及基于向量数据库的长期记忆系统。

## 🌟 核心特性

- **分层能力架构 (Tiered Capability)**:
    - **Tier 1 (基础工具)**: 稳定、高速的系统级工具（文件读写、终端执行、记忆检索）。
    - **Tier 2 (动态技能)**: 模块化、可插拔的技能扩展。支持独立的 `skill.json` 定义和环境隔离。
- **主动记忆闭环 (The Memory Loop)**: 
    - **静默检索 (RAG)**: 每轮对话前自动检索历史相关知识。
    - **自主反思 (Reflection)**: 任务完成后自动提取并保存关键事实到长期记忆库。
- **专业级联网能力**: 集成 Tavily AI Search，提供具备智能摘要和来源引用的专业搜索结果。
- **安全隔离与灵活性**: 
    - 针对本地开发优化的路径安全机制，支持子目录自动创建。
    - 支持 Docker 物理隔离与宿主机逻辑隔离两种模式。
- **多模型支持**: 通过 LiteLLM 无缝接入 Gemini, Gemma, GPT-4, Claude 等主流大模型。

## 🚀 快速开始

### 1. 环境准备
确保已安装：
- Docker & Docker Compose
- Python 3.10+ (推荐使用 venv)

### 2. 配置环境变量
复制 `env_example` 并重命名为 `.env`，配置你的 API Key：
```env
GOOGLE_API_KEY=your_google_ai_studio_api_key
MODEL_NAME=gemini/gemini-1.5-flash
TAVILY_API_KEY=your_tavily_key
DATABASE_URL=postgresql://tars:tars_pass@localhost:5432/tars_db
```

### 3. 启动基础设施
```bash
docker-compose up -d db
```

### 4. 运行交互式 Agent
```bash
# 安装依赖
pip install -r requirements.txt
# 运行
./tars -it
```

## 📂 项目结构
- `app/`: 核心逻辑。
    - `agent.py`: ReAct 循环与反思逻辑。
    - `skills.py`: 动态技能加载引擎。
    - `tools.py`: 基础工具集（Tier 1）。
- `app/skills/`: 动态技能存放地（Tier 2）。
- `data/`: Agent 的工作空间，受路径安全机制保护。
- `logs/`: 自动切分的运行日志。

## 📖 相关文档
- [WALKTHROUGH.md](./walkthrough.md): 最近一次架构升级与修复记录。
- [SOUL.md](./SOUL.md): Agent 的核心准则、价值观与性格定义。
- [TODO.md](./TODO.md): 待办功能与技术规划。

---
*Stay Human. Stay Tars.*
