# Tars Agent 开发进度

## 核心任务
- [x] 初始化项目结构与 Docker 环境
- [x] 实现基础数据库持久化 (PostgreSQL + PGVector)
- [x] 实现核心 ReAct 思考循环
- [x] 封装基础工具集 (文件操作, 终端执行)
- [x] 跑通第一个端到端集成测试 (MVP)
- [ ] 实现基于向量数据库的长期记忆 (RAG)
- [ ] 优化性格与 System Prompt (SOUL.md)
- [ ] 增强工具箱 (Web Search, Memory Search)

## 待办事项
- [ ] 增加 `memory` 工具，支持存入和查询向量数据库
- [ ] 优化 CLI 输出格式，支持 Markdown 渲染
- [ ] 添加 Web 搜索工具 (Tavily/Serper)
- [ ] 编写单元测试，提高代码健壮性
