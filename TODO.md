# Tars Agent 待办事项与技术注意事项

## 🚀 待办功能 (Features)
- [ ] **长期记忆增强**: 支持多知识库切换（如：个人生活、技术文档、项目资料）。
- [ ] **向量迁移脚本**: 当 `EMBEDDING_MODEL` 变更时，自动读取旧数据并使用新模型重新生成向量。
- [ ] **技能自我安装**: 实现 `install_skill` 核心工具。
- [ ] **RAG 引用标注**: 在回答时指明信息是从哪条记忆中提取的。

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
