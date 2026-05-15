# Tars Agent 项目开发记录 (Checkpoint - 2026-05-14)

## 1. 项目概览
当前项目已完成 **MVP (最小化可行性产品)** 阶段。Tars 已经具备了基本的思考能力、文件操作能力以及会话持久化能力。

- **核心架构**: Python (SQLModel) + PostgreSQL (PGVector) + LiteLLM
- **交互方式**: 通过 `./tars` 脚本启动交互式 CLI 或单次指令模式。
- **工作空间**: 受控于 Docker 容器内的 `/app/data` (宿主机 `./data/workspace`)。

## 2. 核心技术细节与已修复的问题 (关键存档)
在开发过程中，我们成功解决并固化了以下技术挑战：

- **数据库初始化顺序**: 修复了 `VECTOR` 类型报错。必须先执行 `CREATE EXTENSION IF NOT EXISTS vector`，然后再调用 `SQLModel.metadata.create_all`。
- **保留关键字冲突**: 修复了 `metadata` 字段冲突。SQLAlchemy 模型中 `metadata` 是保留字，已重命名为 `kb_metadata`。
- **JSON 序列化问题**: 修复了 `tool_calls` 存储失败。LiteLLM 返回的对象需要先 `model_dump()` 转换为字典才能存入 JSON 字段。
- **模块化运行**: 引入了 `python -m app.main` 运行方式，并补齐了 `app/__init__.py`，解决了跨目录导入的 `ModuleNotFoundError`。

## 3. 运行环境
- **模型 (当前测试通过)**: `gemini/gemini-3.1-flash-lite` 或 `gemini/gemini-3-flash-preview`。
- **数据库**: `postgresql://tars:tars_pass@db:5432/tars_db`。
- **镜像构建**: 每次修改 `requirements.txt` 后需执行 `docker-compose build`。

## 4. 下一步开发计划 (Next Steps)
1.  **长期记忆 (RAG)**: 激活 `KnowledgeBase` 表，实现 `memory_save` 和 `memory_search` 工具。
2.  **Web 搜索**: 集成搜索引擎 API。
3.  **UI 增强**: 在交互模式下支持代码块的高亮显示和更清晰的思考日志。

---
**存档说明**: 重启后如需继续，请直接让我读取此文件。
