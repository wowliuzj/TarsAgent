# Changelog

## [2.2.0] - 2026-05-17
### 🤝 核心进化：Phase 2 多角色协作落地 (Multi-Agent)
Tars 现已实现了内部的“三权分立”，具备了独立进行任务拆解与结果自我审计的能力。

#### 核心升级
- **Planner (规划者) 节点**: 作为图入口，负责解析用户意图并将其拆解为线性的执行计划 (`SubTask` 列表)。
- **Executor (执行者) 演进**: 增加了专属的系统提示词约束，使其严格遵循 Planner 生成的计划按步骤执行。
- **Auditor (审计员) 节点**: 在任务结束前拦截输出，负责验证任务的准确性、安全性和完整性。建立了完善的自我纠错闭环（支持驳回至 Executor 重试最多 3 次，或退回 Planner 重新规划）。
- **状态层支持 (`TarsState`)**: 增加了多智能体控制流追踪字段 (`current_task_index`, `executor_retries`, `planner_retries`, `audit_feedback`)。

## [2.1.0] - 2026-05-16
### 🧠 核心重构：从 ReAct 循环迁移至 LangGraph 状态机
Tars 的核心调度引擎已正式告别简单的 `while` 循环，升级为基于 **LangGraph** 的有向无环图 (DAG) 编排架构。这标志着 Tars 从单线程脚本进化为可扩展的多 Agent 系统。

#### 核心升级
- **LangGraph 编排引擎**: 实现了 `THINK -> EXECUTE -> REFLECT` 的结构化流转。
- **并行执行能力**: 支持在单次决策中并发调用多个 MCP 工具（如同时发起多个搜索请求），显著降低复杂任务延迟。
- **THP (Tars Harness Protocol)**: 正式确立了基于 Pydantic 的状态约束协议，确保所有节点间的数据交互标准化。
- **状态持久化准备**: 引入了 `TarsState` 统一状态模型，为后续的“脱水/复写”和断点续传功能打下基础。

#### 修复与优化
- **异步资源清理**: 修复了 MCP 服务在退出时可能出现的 `RuntimeError` 异步清理冲突。
- **工具调用冲突**: 修复了发送给 LiteLLM 的消息中 `tool_calls` 格式不兼容 OpenAI 标准的问题。
- **极简执行强化**: 强化了系统提示词，严禁在专业工具提供数据后进行冗余的网页搜索。

## [2.0.0] - 2026-05-16
### 🚀 架构大升级：全面拥抱 MCP (Model Context Protocol)
Tars 现已从传统的脚本化技能系统全面迁移至 Anthropic 的 MCP 标准架构，实现了真正的模块化与插件化。

#### 核心特性
- **MCP 调度器 (MCPClientManager)**: 实现了动态的服务发现与工具编排，支持标准 JSON-RPC 通信。
- **懒加载 (Lazy Loading)**: 启动时不再冷启动所有容器，仅在首次调用工具时按需激活，显著提升启动速度。
- **环境持久化**: 引入 Docker Volume 挂载技术，容器内的 Python 依赖包只需安装一次，重启秒开。
- **双层安全模型**:
    - **Native 模式**: 用于 `system_runtime` 等核心组件，提供高性能本地访问。
    - **Docker 沙盒模式**: 用于第三方扩展，提供物理级别的安全隔离。
- **自愈式联网**: 自动识别宿主机代理并将 `127.0.0.1` 映射为 `host.docker.internal`，解决沙盒内联网安装依赖的痛点。

#### 优化与修复
- **极简执行原则**: 优化系统提示词，严禁模型在未授权情况下进行非必要的跨工具调度。
- **垂直领域优先**: 强制模型优先使用专门的 MCP Server（如金融、代码）而非通用搜索。
- **清理 Legacy**: 彻底移除了 `app/skills/` 和旧版 `tools.py`。

## [2026-05-15] - OpenAI 迁移与权限架构优化

### 🚀 核心升级
- **OpenAI + Gemini 混合架构 (Hybrid LLM Architecture)**:
    - 迁移至 OpenAI 作为主推理模型（支持 `openai/gpt-5-mini`），显著提升了逻辑推理与指令遵循的稳定性。
    - 保留 Google Gemini 作为高效向量 Embedding 模型，实现性能与成本的最佳平衡。
- **权限边界重构 (Security & Path Access)**:
    - **取消 WORKSPACE_DIR 硬性限制**：为了支持 Agent 读取项目根目录（如 `SKILLS_GUIDE.md`）进行自主学习，放开了原本局限在 `data/` 目录的沙箱。
    - **实施敏感文件黑名单 (Sensitivity Blacklist)**：引入了 `SENSITIVE_FILES` 保护机制，强制禁止 Agent 通过工具访问 `.env`、`.git`、`config.json` 等关键隐私文件，兼顾了灵活性与安全性。

### 🛠️ 技能开发 (Skill Optimization)
- **`crypto_price` 深度增强**:
    - 实现了 **Binance, OKX, Coinbase, CoinGecko** 四家主流交易所的并行报价聚合。
    - 引入了 `ThreadPoolExecutor` 并行请求，解决了单点故障和响应延迟问题。
    - 增加了智能符号识别（如 `BTCUS` 自动补全为 `BTCUSDT`）与反爬虫 User-Agent 伪装。
- **技能参数传递修复**: 解决了 `app/tools.py` 中 `make_skill_executor` 闭包对参数解包不当导致的工具调用崩溃问题。

### 🐞 环境与调试
- **环境自检工具 (`list_models.py`)**: 重写为混合环境检测脚本，可一键验证 OpenAI 和 Google API 的连通性。
- **配置同步**: 同步更新了 `.env` 和 `env_example`，明确了多模型 Key 的强制配置要求。

### [0.3.0] - 2026-05-15

### 🚀 架构级重大升级
- **模块化技能体系 (Standardized Skills)**:
    - 引入 NPM 风格的 `skill.json` 清单标准（支持 `version`, `main`, `runtime`）。
    - 实现了技能依赖自动管理：启动时自动扫描并安装技能目录下的 `requirements.txt`。
    - 支持多语言运行环境：现在可以无缝执行 Python, Node.js 和 Shell 编写的技能。
- **环境持久化 (Docker Persistence)**:
    - 在 `docker-compose.yml` 中引入 `python_libs` 卷，确保 Agent 在运行时安装的依赖库在容器重启后依然保留。
- **动态性能控制**:
    - 将 `MAX_STEPS` 接入环境变量，默认上限提升至 20 步，大幅增强了处理复杂 Excel 对比等长链路任务的能力。

### 🛠 稳定性与性能
- **输入清洗**: 在 `app/main.py` 引入 UTF-8 自动脱敏逻辑，彻底杜绝特殊字符导致的崩溃。
- **输出静默**: 深度隐藏了 LiteLLM 的反馈建议 and 调试信息，控制台输出更纯净。
- **Embedding 升级**: 适配 `gemini/gemini-embedding-2`，向量维度提升至 3072，语义检索更精准。

### 🛠️ 技术参数记录
- **向量数据库**: 升级至 `gemini-embedding-2` (3072 维度)，提供更高精度的语义匹配。
- **内存架构**: 确立了“前置检索 + 后置反思”的完整记忆闭环。

## [2026-05-14] - MVP 核心闭环达成

### 🚀 核心功能 (Core Features)
- **容器化编排**: 实现了 Python 应用与 PostgreSQL (带 PGVector 扩展) 的 Docker Compose 完整链路。
- **ReAct 思考引擎**: 在 `app/agent.py` 中构建了核心循环，支持模型自主决策并调用工具。
- **快捷交互**: 提供了 `./tars` 快捷脚本，支持 `-it` 交互式对话和单次 CLI 指令。
- **持久化记忆**: 实现了会话 (Session) 与消息 (Message) 的数据库持久化，确保对话历史可追溯。

### 🛠 工具系统 (Tools)
- **文件操作**: 增加了 `read_file`, `write_file`, `list_files` 工具，限定在 `/app/data` 安全沙箱内。
- **终端执行**: 增加了 `run_terminal_command`，允许 Agent 执行 Shell 指令（如获取实时金融数据）。

### 🐞 关键修复 (Bug Fixes)
- **DB 初始化**: 解决了 `VECTOR` 类型识别失败问题（通过调整 `CREATE EXTENSION` 的执行顺序）。
- **字段冲突**: 将 `KnowledgeBase` 的 `metadata` 字段重命名为 `kb_metadata`，规避 SQLAlchemy 保留字冲突。
- **SSL 补丁**: 在 Dockerfile 中补全了 `ca-certificates`，修复了容器内无法进行 HTTPS 请求的 Exit Code 35 错误。
- **序列化修复**: 实现了 `tool_calls` 到 JSON 字典的转换逻辑，修复了数据库提交时的序列化异常。

### 🎨 UI/UX 改进
- **思考面板**: 使用 `Rich.Panel` 实时展示模型每一轮的思考逻辑。
- **请求追踪**: 增加了每次 API 调用时显示 Step 数及模型名称的实时状态条。

---
## [1.5.0] - 2026-05-14
- 实现基于 SQLModel 的异步数据库操作。
- 引入 pgvector 向量检索实现长期记忆。
