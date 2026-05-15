# Tars Agent Changelog

所有对 Tars Agent 项目的重要变更都将记录在此文件中。

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
