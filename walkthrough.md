# Tars Agent 升级回顾：OpenAI 迁移与安全权限重构

## 1. 核心迁移：迈向 OpenAI
为了提升 Agent 的逻辑推理稳定性与并发处理能力，我们完成了从纯 Gemini 架构到 **OpenAI + Gemini 混合架构** 的平滑迁移。

- **主推模型**: 升级为 `openai/gpt-4o` (或 `gpt-5-mini`)。
- **向量模型**: 保留 `gemini/gemini-embedding-2`。
- **环境验证**: 重写了 `list_models.py`，支持一键检测双 API 环境的连通性。

## 2. 权限架构优化：自由与安全的平衡
我们重构了 `app/tools.py` 中的路径访问逻辑，解决了 Tars “看不见”根目录文档的问题。

- **权限开放**: 删除了 `WORKSPACE_DIR` 的强制沙箱限制。Agent 现在可以读取项目根目录下的文件（如 `SKILLS_GUIDE.md`），使其具备了自主学习项目规范的能力。
- **黑名单保护**: 引入了 `SENSITIVE_FILES` 黑名单过滤机制。
  - **受限文件**: `.env`, `.git`, `config.json`, `id_rsa` 等。
  - **效果**: 即使 Agent 尝试强行读取或列出这些文件，也会被底层逻辑拦截，确保 API Key 和私钥的安全。

## 3. 技能实战：`crypto_price` 深度增强
作为新架构下的首个实战优化，我们对加密货币行情技能进行了重写：
- **多交易所并行**: 同时从 Binance, OKX, Coinbase, CoinGecko 获取数据。
- **并发优化**: 引入 `ThreadPoolExecutor`。
- **健壮性**: 解决了之前的 `403 Forbidden` 问题，并增加了异常值过滤与自动补全逻辑。

## 4. 验证与结果
- **功能测试**: 成功运行 `crypto_price` 获取了聚合报价。
- **路径测试**: 成功让 Tars 在没有显式提示的情况下通过读取 `SKILLS_GUIDE.md` 完成了技能目录结构的调整。
- **安全性测试**: 验证了 Tars 无法读取 `.env` 文件的保护逻辑。

---
*Next Step: 进一步优化技能沙盒的依赖预装逻辑，以及增强 RAG 的多轮反思深度。*
