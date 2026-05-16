# Tars Agent 待办事项与技术注意事项

## 🚀 待办功能 (Features)
- [x] **长期记忆增强**: 已实现基于 PGVector 的长期记忆库。
- [x] **MCP 标准化**: 全面迁移至 Anthropic MCP 总线架构，支持插件式扩展。
- [x] **异步驱动引擎**: 核心循环已升级为 `asyncio`。
- [ ] **向量迁移脚本**: 当 `EMBEDDING_MODEL` 变更时，自动重索引。
- [ ] **MCP 生态扩展**: 集成更多外部 MCP Servers (GitHub, Slack, etc.)。
- [x] **RAG 引用标注**: 已在搜索结果中包含内容摘要。

## ⚠️ 关键注意事项 (Gotchas)
- **RAG 维度锁定**: 
    - 数据库的 `vector` 字段在创建时必须固定维度。
    - **变更模型后果**: 必须 `DROP TABLE knowledge_base`，否则会报维度不匹配错误。
    - **数据保留**: 必须在删除前导出 `content` 文本，并用新模型重新向量化（Re-embedding）。
- **Tavily 额度**: 免费版每月 1000 次，注意监控调用频率。
- **SSL 协议**: 在某些受限网络下，Gemini API 可能会报 `EOF occurred in violation of protocol`，需检查代理服务器的 TLS 版本。

## 🛠️ 运维与调试
- **日志查看**: 定期清理 `logs/` 目录下的 `.html` 调试快照。
- **数据库备份**: 生产环境部署前，需通过 `pg_dump` 备份 `sessions` 和 `knowledge_base` 表。
