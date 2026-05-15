# Tars Agent 项目开发记录 (Checkpoint - 2026-05-15)

## 1. 项目概览
当前项目已从 MVP 进化为 **模块化架构 (Tiered Capability)**。Tars 具备了分层能力，并能通过外部模块动态扩展其“技能 (Skills)”。

- **核心架构**: 引入了 Tier 1 (系统工具) 与 Tier 2 (模块化技能) 的分层设计。
- **技能加载**: 实现了动态扫描 `app/skills/` 目录并根据 `skill.json` 自动注册工具的引擎。
- **外部集成**: 接入了 Tavily AI Search 专业级联网能力。

## 2. 核心技术细节与已修复的问题 (关键存档)
- **SSL/网络连接问题**: 修复了原生爬虫由于代理 IP 被拦截（人机验证）导致的 `ConnectError`。已全面切换至 Tavily API 接口，确保了联网搜索的稳定性。
- **ImportError 修复**: 修复了 `app/skills.py` 中缺失 `DYNAMIC_SKILL_TOOLS` 定义导致的启动失败问题。现在已实现完善的动态扫描逻辑。
- **WORKSPACE_DIR 修复**: 修复了 `.env` 中 `WORKSPACE_DIR` 路径错误（`app/data` -> `data`）导致的工具执行异常。
- **子目录支持与安全增强**: 改进了 `app/tools.py` 中的路径处理逻辑。现在支持安全的子目录读写，并能在写入时自动创建不存在的目录，解决了 Agent 无法在子文件夹中运行脚本的问题。

### 🏗️ 核心运行环境 (Runtime)
- **输入清洗 (Main Loop)**: `app/main.py` 自动过滤用户输入中的特殊字符。
- **动态深度**: 通过 `.env` 中的 `MAX_STEPS` 控制 Agent 的最大思考步数。
- **持久化依赖**: Docker 容器通过 `python_libs` 卷挂载了 `/usr/local/lib/python3.10/site-packages`，使得 Agent 自行安装的库在重启后依然有效。

### 🧩 模块化技能开发 (Skills System)
现在的技能开发遵循以下标准结构：
- **目录**: `app/skills/[skill_name]/`
- **清单**: `manifests/skill.json` (使用 `main` 指定入口，`runtime` 指定环境)。
- **依赖**: 根目录下的 `requirements.txt` (系统启动时会自动扫描并安装)。
- **入口**: 默认 `src/executor.py`，参数以 JSON 字符串形式传入命令行。
- **增强型日志管理**: 引入了按日期切分的日志系统 (`logs/tars-YYYY-MM-DD.log`)，并将控制台冗长的 Traceback 报错重定向至静默日志中，极大提升了 UI 交互的清爽度。
- **动态参数校验**: 利用 `skill.json` 中的 JSON Schema，让 LLM 在调用技能时能自动遵循参数约束。
- **RAG 维度锁定 (重要)**: 确立了基于环境变量的 `EMBEDDING_DIM` 配置。
- **主动记忆闭环 (The Memory Loop)**: 
    - **前置检索**: Agent 在响应前会静默执行向量搜索，将相关记忆注入 Prompt。
    - **后置反思**: 引入了 Reflection 步进，让 Tars 在任务结束后自主提取并保存关键事实（偏好、修正、重要数据）。

## 3. 运行环境
- **模型建议**: 推荐使用 `gemini/gemini-1.5-flash` 或 `gemini/gemma-4-26b-a4b-it`。
- **向量维度**: 默认配置已升级至 **3072** 维（适配 `gemini-embedding-2`）。
- **输入净化**: 系统已内置 UTF-8 强力清洗逻辑，兼容包含控制字符的终端输入。
- **容器挂载**: 新增了 `./app/skills` 和 `./logs` 的挂载，支持热更新技能。

## 4. 下一步开发计划 (Next Steps)
1.  **技能自我学习 (Agentic Self-Improvement)**: 实现 `install_skill` 工具，让 Tars 能通过对话自主编写、测试并安装新的 Tier 2 技能。
2.  **长期记忆 (RAG) 激活**: 利用现有的 `KnowledgeBase` 表，将搜索到的有用信息持久化到向量数据库。
3.  **UI/UX 进一步增强**: 为交互式 Prompt 添加自动补全支持，或在 Web UI 层面进行探索。

---
**存档说明**: 重启后如需继续，请直接让我读取此文件。
