# Tars Agent 2.0 (MCP Edition)

Tars Agent 是一个基于 Python 构建的高性能、工业级 AI 智能体。它全面采用了 Anthropic 的 **Model Context Protocol (MCP)** 标准，实现了高度解耦、物理隔离且具备自进化能力的插件化架构。

## 🏗️ 2.0 架构 (LangGraph + MCP)

Tars 2.0 采用了 **THP (Tars Harness Protocol)** 协议，通过 **LangGraph** 驱动任务流转：

```mermaid
graph LR
    User([用户输入]) --> PM{Planner/PM}
    PM --> Ex[Executor]
    Ex --> Au{Auditor}
    Au -- 驳回 --> Ex
    Au -- 通过 --> Ref[Reflect/Save]
    Ref --> User
```

- **LangGraph**: 核心逻辑骨架，负责状态流转与节点调度。
- **MCP (Model Context Protocol)**: 工具层的统一协议，支持 Docker 沙箱化运行。
- **LiteLLM**: 多模型适配层，支持 OpenAI, Claude, Gemini, DeepSeek 等主流 LLM。
- **`/app/mcp`**: 核心调度中心 (`client_manager.py`)，负责 Server 发现与 JSON-RPC 通信。
- **`/mcp_servers`**: 技能插槽目录。每个子文件夹都是一个独立的 MCP 服务。
    - **`system_runtime`**: 提供文件读写、终端、记忆等核心能力 (Native 运行)。
    - **`crypto_market`**: 提供实时行情聚合 (Docker 沙箱运行)。
    - **`web_search`**: 提供联网搜索能力 (Docker 沙箱运行)。

- **懒加载 (Lazy Loading)**: 启动时仅扫描元数据。只有当你明确调用某个工具时，Tars 才会启动对应的 Docker 容器或进程，实现“零延迟启动”。
- **物理隔离沙盒**: 第三方扩展默认运行在 Docker 容器中，确保你的宿主机环境安全。
- **环境自愈与持久化**: 容器内自动安装依赖，并利用 Docker Volume 持久化 Python 环境，避免重复安装。

## 🚀 快速开始

### 1. 环境准备
- Docker & Docker Compose
- Python 3.10+

### 2. 配置与启动
1. 复制 `env_example` 并配置 `.env`（需包含 `OPENAI_API_KEY` 和 `TAVILY_API_KEY` 等）。
2. venv/bin/activate
3. 启动数据库：`docker-compose up -d db`。
4. 运行 Tars：
   ```bash
   pip install -r requirements.txt
   ./tars
   ```

## 📖 相关文档
- [WALKTHROUGH.md](./walkthrough.md): 记录了从 Legacy 到 MCP 的详细演变。
- [MCP_GUIDE.md](./MCP_GUIDE.md): 开发者指南，教你如何为 Tars 编写新的 MCP Server。
- [CHANGELOG.md](./CHANGELOG.md): 版本变更历史。

---
*Stay Human. Stay Tars.*
