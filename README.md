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
- **多模型混合架构 (Hybrid Architecture)**: 
    - **高度灵活**: 通过 LiteLLM 适配层，支持 OpenAI, Google, Claude, DeepSeek 等多种主流 LLM 模型。
    - **配置驱动**: 系统根据 `.env` 配置自动切换主推理模型与向量模型，实现推理与检索能力的动态平衡。
    - **核心约束**: 向量模型（Embedding）与向量数据库强绑定。如需更换向量模型，必须对现有向量数据库进行全量迁移/重索引。
- **动态安全防护**: 
    - 支持项目根目录全局访问，Agent 可自主阅读 `SKILLS_GUIDE.md` 等文档进行技能学习。
    - 内置 **敏感文件黑名单**，自动屏蔽 `.env`、`.git` 等核心隐私文件。
- **物理隔离沙盒**: 针对联网和高风险技能，支持 Docker 容器级物理隔离运行。

## 🚀 快速开始

### 1. 环境准备
确保已安装：
- Docker & Docker Compose
- Python 3.10+ (推荐使用 venv)

### 2. 配置环境变量
复制 `env_example` 并重命名为 `.env`。**根据你选择的模型提供商配置对应的 API Key：**
```env
# 主推理模型 (示例使用 OpenAI)
OPENAI_API_KEY=your_openai_key
MODEL_NAME=openai/gpt-4o

# 向量模型 (示例使用 Google，更换模型需重索引数据库)
GOOGLE_API_KEY=your_google_key
EMBEDDING_MODEL=gemini/gemini-embedding-2
```

### 3. 启动基础设施
```bash
docker-compose up -d db
```

### 4. 运行交互式 Agent
```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
# 安装依赖
pip install -r requirements.txt
# 运行
./tars
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
