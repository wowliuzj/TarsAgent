# Tars Agent 项目开发记录 (Checkpoint - 2026-05-15)

## 1. 项目概览
当前项目已从 MVP 进化为 **模块化架构 (Tiered Capability)**。Tars 具备了分层能力，并能通过外部模块动态扩展其“技能 (Skills)”。

- **核心架构**: 引入了 Tier 1 (系统工具) 与 Tier 2 (模块化技能) 的分层设计。
- **技能加载**: 实现了动态扫描 `app/skills/` 目录并根据 `skill.json` 自动注册工具的引擎。
- **外部集成**: 接入了 Tavily AI Search 专业级联网能力。

## 2. 核心技术细节与已修复的问题 (关键存档)
- **SSL/网络连接问题**: 修复了原生爬虫由于代理 IP 被拦截（人机验证）导致的 `ConnectError`。已全面切换至 Tavily API 接口，确保了联网搜索的稳定性。
- **模块化 Skill 设计**: 确立了 `manifests/skill.json` (语义) + `src/executor.py` (逻辑) 的标准结构，实现了声明与实现的分离。
- **增强型日志管理**: 引入了按日期切分的日志系统 (`logs/tars-YYYY-MM-DD.log`)，并将控制台冗长的 Traceback 报错重定向至静默日志中，极大提升了 UI 交互的清爽度。
- **动态参数校验**: 利用 `skill.json` 中的 JSON Schema，让 LLM 在调用技能时能自动遵循参数约束（如 Symbol 必须大写等）。

## 3. 运行环境
- **模型建议**: 推荐使用 `gemini/gemini-1.5-flash` 以获得更好的工具调用稳定性。
- **搜索服务**: 需要在 `.env` 中配置 `TAVILY_API_KEY`。
- **容器挂载**: 新增了 `./app/skills` 和 `./logs` 的挂载，支持热更新技能和宿主机直接查看日志。

## 4. 下一步开发计划 (Next Steps)
1.  **技能自我学习 (Agentic Self-Improvement)**: 实现 `install_skill` 工具，让 Tars 能通过对话自主编写、测试并安装新的 Tier 2 技能。
2.  **长期记忆 (RAG) 激活**: 利用现有的 `KnowledgeBase` 表，将搜索到的有用信息持久化到向量数据库。
3.  **UI/UX 进一步增强**: 为交互式 Prompt 添加自动补全支持，或在 Web UI 层面进行探索。

---
**存档说明**: 重启后如需继续，请直接让我读取此文件。
