# Tars Agent Changelog

所有对 Tars Agent 项目的重要变更都将记录在此文件中。

## [2026-05-15] - 架构升级与技能模块化

### 🚀 新增功能
- **模块化技能架构 (Modular Skills)**: 实现了“声明与实现分离”的标准 Skill 结构。每个技能拥有独立的 `manifests/skill.json` (语义声明) 和 `src/executor.py` (执行逻辑)。
- **动态技能加载引擎**: Tars 启动时会自动扫描并注册 `app/skills/` 下的所有模块化技能，无需手动修改代码。
- **专业级 AI 搜索 (Tavily)**: 集成 Tavily AI Search，彻底解决了原生爬虫被反爬（人机验证）拦截的问题，提供高质量的智能摘要。
- **增强型日志系统**: 实现了按日期自动切分的日志系统 (`logs/tars-YYYY-MM-DD.log`)。
- **长期记忆 (RAG) 自动化**: 
    - **静默检索**: 在每轮对话前自动进行向量搜索，获取历史相关背景。
    - **自主反思 (Reflection)**: 借鉴 Hermes 架构，在任务完成后自主判断并保存重要事实到记忆库。
- **提示词中心化**: 引入 `app/prompts.py` 统一管理系统指令和反思模板。

### 🛠️ 技术优化
- **异常拦截优化**: 彻底隐藏 LiteLLM 和 HTTPX 的控制台输出，屏蔽冗余的调试提示。
- **输入鲁棒性修复**: 增加了用户输入的 UTF-8 自动净化逻辑，解决了终端回退符导致的编码崩溃问题。

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
- **输出静默**: 深度隐藏了 LiteLLM 的反馈建议和调试信息，控制台输出更纯净。
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
*记录人: Antigravity & User*
