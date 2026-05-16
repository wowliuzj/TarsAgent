# Changelog

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
确立了“前置检索 + 后置反思”的完整记忆闭环。

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
