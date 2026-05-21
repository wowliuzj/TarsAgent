# Changelog

## [2.6.0] - 2026-05-21
### 🪐 契约立身：Tars 约束协议 2.0 (THP 2.0) 与 L6 高精密自愈沙箱上线
Tars 2.0 迎来了软件工程级重大升级，正式落地多智能体强类型数据契约（Harness Engineering）、图节点级状态机双向不变量断言校验、动态 Token 上下文滑动窗口，以及 L6 精密事务的本地 pytest 自动测试与自愈重构回路。这标志着 Tars 从不确定的提示词调试阶段迈入了契约驱动的工程智能体时代。

#### 核心特性
- **强类型数据契约与 LiteLLM 结构化输出封装 (`app/mcp/state.py` & `app/agent.py`) [NEW]**:
  - 构建了 `PlannerOutput`、`ExecutorThought` 和 `AuditorVerdict` Pydantic v2 模型契约。
  - 通过 `response_format` 参数将类型契约注入 LiteLLM 接口，强制模型输出 OpenAI/LiteLLM 兼容的 100% 类型安全结构化 JSON，废弃了原版脆弱的 text/regex 正则文本提取。
  - Executor 节点在工具调用时，在 text 内容中遵循嵌套式 thought JSON 契约以兼顾特种工具集调用与结构化思考。
- **契约级前后置状态机不变量断言校验 (`verify_state_invariants` in `app/mcp/graph.py`) [NEW]**:
  - 在 LangGraph 的 `planner`、`think`、`auditor` 等关键图节点运转的前后置时机，强制部署运行时不变量校验（Invariants Assertions）。
  - 严格审计拆解计划的合法性（precision 评级必在 L1~L6）、置信度有效性、以及工作区路径清白度，防止在极端复杂行程下的“记忆漂移”与状态机污染。
- **智能 Token 历史滑动窗口剪裁器 (`prune_history_messages` in `app/mcp/graph.py`) [NEW]**:
  - 针对大型重构等超长行程中因物理工具输出巨量日志导致的 Token 膨胀及上下文溢出问题，开发了局部滑动裁剪策略。
  - 在总历史长度超警戒线时，在内存只读副本中自动对旧版 `ToolMessage` 日志做压缩和有损截断，而 100% 完整保留 System 指南、Mission 目标及 AIMessage 对话上下文。既精减了 Token 消耗，又确保了 LangGraph DB 持久化 Ledger 的回放完整性。
- **L6 高精密 Sandbox pytest 测试与自愈回路 (`register_step_node` in `app/mcp/graph.py`) [NEW]**:
  - 针对 precision 等级为 `L6` (高精度代码生成或系统修改) 的极端精密子任务，在节点提交前，自动在隔离物理沙箱内拉起 pytest 测试套件。
  - 一旦测试失败（退出码 != 0），框架强行锁定当前步进索引，并将 pytest traceback 报错日志以 System 反馈喂回 Executor，驱动智能体利用编译器报错精准进行自主代码重构，直至通过率 100% 绿色后才流转至 Auditor 审计。重试上限配置为 `MAX_EXECUTOR_RETRIES` (默认 3 次) 以优雅退避。
- **成果脱壳提炼与双重防御机制 (Response Unwrapping) [NEW]**:
  - **问题根源**：由于全局强制执行结构化输出（OpenAI Structured Outputs / 嵌套 JSON），导致在闲聊及极简对话场景中，AI 最终合成结果包含了内部调试 JSON（包含 `reasoning`, `confidence` 等字段），直接破坏了面向用户的最终界面纯净度。
  - **双重纵深防御**：
    1. *第一层 (快速通道直接旁路)*：在 `reflect_node` 进行快速旁路判定前，自动解析 `step_1_result` JSON，若符合协议则在内存中提取 `reasoning` 部分，恢复 `is_simple_chat` 标志位，直接绕过成果大合成，零 Token 消耗极速返回给用户。
    2. *第二层 (兜底成果脱壳)*：在 `TarsAgent.run` 的尾部提取阶段部署兜底防御，自动检测并对倒序历史的 AIMessage 剥离 JSON 封皮提取 `reasoning`，实现底层严苛强契约通信与用户终端友好自然语言的完美解耦。
  - **集成测试与回归保障**：在 `tests/test_harness_contracts.py` 中新增 `test_response_unwrapping_double_defense`，保证了两层脱壳逻辑的绝对稳健与 100% 回归成功。
- **完备的集成契约测试集与规范文档 (`docs/HARNESS_ENGINEERING.md`) [NEW]**:
  - 编写了详尽的高精度 Harness 约束协议设计规范书；在 `tests/test_harness_contracts.py` 中编写了覆盖强类型解析、不变量断言拦截、Token 滑动窗口剪裁、以及 L6 sandbox pytest 报错自愈回路的 7 大高品质集成单元测试，测试通过率 100%。

## [2.5.0] - 2026-05-20
### 🛡️ 稳如磐石：双重纵深防御安全红线与人机协同介入机制 (HITL & Sandbox)
Tars 2.0 在物理大解放（彻底放开对代码与测试目录的自由修改，激活全面生产力）的同时，上线了固若金汤的物理安全屏障与人机交互介入策略，达成开发自由度与信息资产安全性之间的极致平衡。

#### 核心特性
- **服务端绝对物理沙箱屏障 (`mcp_servers/system_runtime/src/server.py`) [NEW]**:
  - 在终端指令物理执行前部署底层防线，使用绝对字符串包含匹配，无死角阻断以任何字符拼接、等于号变形（如 `--git-dir=.git`）绕过的 `sudo`/`su` 特权操作及 `.env` / `.git` / `id_rsa` / `config.json` 等敏感文件探测，违规时在物理底层直接抛出 `PermissionError` 终止流程。
- **客户端人机协同确认机制 (Client-Side HITL Interceptor)**:
  - **置信度自评解析 (`parse_confidence`)**：自动从 Executor 思考块中解析 `Confidence: <score>` 安全分数。
  - **高危终端指令风险审计 (`check_command_risk`)**：设计了涵盖特权提升、敏感文件操作、反弹监听/后门、毁灭性删除核心代码、权限强改 (`chmod`/`chown`/`chgrp`) 以及敏感数据外传 (`curl`/`wget` POST 标志) 的 6 大深度拦截审计规则。
  - **精美 Rich Panel 交互提示**：当 Executor 自评置信度低于安全阈值线（普通工具默认 `0.85`，终端命令默认 `0.95`）或触发高危指令警告时，在控制台弹出高阶警报交互面板，由人类控制者决定放行或安全终止。若用户手动拒绝，Tool 节点将输出友好阻断回执促使 AI 进行完美自愈重规。
- **动态环境变量阈值配置与热拔插 (`BASE_CONFIDENCE_THRESHOLD` & `TERMINAL_CONFIDENCE_THRESHOLD`)**:
  - 将安全置信度阈值移至 `.env` 与 `env_example`，允许跨环境动态调节置信线。
  - 增强了鲁棒的优雅降级退避行为：若配置格式异常或未指定，自动降级至安全默认值 `0.85` 与 `0.95`，保障主逻辑百分之百稳定。
- **完备的集成安全测试集与环境文档 (`docs/SAFETY_AND_HITL.md`) [NEW]**:
  - 编写了高阶安全规范说明书文档；在 `tests/test_safety.py` 中新增了 `test_dynamic_confidence_thresholds` 及对服务端物理沙箱的完整单元测试。当前项目全部 18 个测试用例通过率达 100%。

## [2.4.0] - 2026-05-19
### 🪐 灵魂觉醒：目标与边界审计转型及灵魂矩阵蓝图
Tars 正式从传统的“命令步骤核对式机器人”蜕变，确立了统一的“单轨人格感官架构”和“安全边界内的创造性变异”法则。Auditor 的底层核验逻辑完成了历史性的重构，释放了 Tars 的主观能动性与智慧涌现潜力。

#### 核心特性
- **目标导向与安全防守审计 (Reconstructed `AUDITOR_PROMPT`)**:
  - 重写审计员判定逻辑：将原本死板的“步骤合同对账”升级为“终极目标导向 (Goal-Oriented)”与“安全红线防守 (Safety Boundary Protection)”双轴审计。
  - 支持创造性变异与路径分叉：明确允许并鼓励 Executor 在执行中根据实际物理状态和灵感，自主探索更高效、高能或更聪明的替代步骤。只要完美解决用户的原始需求（`Mission.goal`）且不踩中系统破坏、隐私泄露等安全红线，予以赞赏放行。
- **灵魂矩阵与记忆升级蓝图 (`SOUL_AND_MEMORY.md`) [NEW]**:
  - 编写了划时代的灵魂矩阵设计文档，明确了 `Warmth`、`Discretion`、`Humour`、`MutationRate` 浮动参数系统，贯穿 Planner -> Executor -> Auditor -> Reflect 全生命周期，保持灵魂的连续一致。
  - 确立了“遗传学记忆链（Evolutionary Memory）”传导机制：被批准的成功变异特征会提炼为进化遗传片段写入长期记忆，自动被 Planner 的后续决策 RAG 动态召回，实现智慧与常识的自我进化与生命化遗传迭代。

## [2.3.0] - 2026-05-18
### 🚀 智感升级：Tool RAG 语义过滤与宏观意图封顶机制
引入了基于 pgvector 向量数据库的 MCP 工具动态召回（Tool RAG）和宏观意图精度拦截器，极大地降低了长行程与复杂任务中的 Token 消耗，解决了 Executor 的 curl 命令行绕远路以及 Auditor 用力过慢导致死循环等痛点。

#### 核心特性
- **MCP 工具 Tool RAG 动态语义索引与召回**:
  - 创建了 `mcp_tool_index` 数据库表，在加载/发现 MCP 服务时，自动通过 `litellm.embedding` 对工具描述计算向量并进行 upsert 缓存同步。
  - 实现工具动态检索：Planner 在决策前自动计算用户 Query 向量，实时召回 Top-K 领域特种工具，并与 100% 默认注入的核心基础设施工具（文件读写、终端及万能搜索）合并。
  - 将过滤后的工具集合以 `<available_tools>` 注入到 Planner 的上下文提示中，使 Planner 能充分感知并精确规划调用专用工具。
- **宏观意图精度截断器 (Macro-Intent Precision Cap)**:
  - Planner 具备检测用户全局口吻意图（如“简单点”、“不要太复杂”）的能力。
  - 一旦捕获简化指示，所有子任务精度等级最高上限强制封顶为 `L3`，从而启动 Auditor 的“柔性审计标准”，并极度合并步骤至 1-3 步，彻底消除了极偏远行程中的大量 Tavily 爬虫卡死重试开销。

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
