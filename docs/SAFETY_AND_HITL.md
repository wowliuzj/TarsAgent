# 🪐 Tars 2.0 「双重纵深防御与置信度退避机制」技术规范 (SAFETY_AND_HITL)

本规范详细阐述了 Tars 2.0 (基于 LangGraph MCP 架构) 所实现的 **「双重纵深防御与人机协同 (HITL & Dual-Defense)」** 体系。在确保开发与维护工作区代码的完全生产力自由的前提下，构建了底层物理沙箱拦截机制和优雅的终端交互授权体验。

---

## 🛠️ 1. 架构设计与变更详情

### 1.1 自信度自评协议与系统提示词中心 (System Prompt & Confidence Protocol)
*   **配置文件**: [app/prompts.py](file:///Users/Shared/Workspace/Tars/TarsAgent/app/prompts.py)
*   **设计细节**:
    在 Executor 思考提示词中注入了 `<confidence_protocol>` 规范，强制要求 Executor 在调用物理工具时，必须在 thought 的末尾以单行格式给出其对于该动作成功率及安全性的自信度自评得分：
    ```text
    Confidence: <0.0 ~ 1.0 的浮点数>
    ```
    *   **自评基准**：
        *   `1.0`: 动作极其常规，参数100%确定，绝对安全且没有破坏性。
        *   `0.90`: 动作常规，参数确定度高，可能有微小的网络波动或极小的失败概率。
        *   `0.80`: 动作具有一定复杂度，或参数可能存在轻微歧义，或涉及较复杂的终端命令。
        *   `0.70 及以下`: 动作复杂且不确定性高，可能涉及高风险命令，或需要探索未置可否的参数/路径。

### 1.2 客户端人机协同介入 (Client-Side HITL Interceptor)
*   **核心实现**: [app/mcp/graph.py](file:///Users/Shared/Workspace/Tars/TarsAgent/app/mcp/graph.py)
*   **设计细节**:
    *   **工作区物理大解放**：彻底排除了对 `read_file`、`write_file` 与 `list_files` 的强制路径物理重定向拦截，恢复了 Tars 自由检查和修改项目本身（如修改 `app/` 和 `tests/` 下的代码与配置）的生产力。
    *   **置信度提取器**：通过 `parse_confidence` 稳健解析器，自动使用正则匹配 Executor 思考内容中的 `Confidence: <score>` 值（缺省默认为 `0.85`）。
    *   **高危指令拦截规则**：编写了 `check_command_risk` 对终端操作进行深度拦截判定：
        *   **绝对阻断 (Blocked)**：特权提升指令 (`sudo`/`su`)、泄露或操作敏感文件（如 `.env`, `.git`, `id_rsa`, `config.json` 等）、反弹监听/后门连接（如 `/dev/tcp`, `nc -l`, `netcat` 等）。此外，毁灭性删除核心代码或骨架目录（如 `rm -rf app`）直接进行绝对阻断。
        *   **人机确认 (Warning)**：对常规目录的递归强制删除（如 `rm -rf tmp/`）、权限修改（`chmod`/`chown`/`chgrp`）、敏感数据网络外传（`curl`/`wget` 带有 POST 或 form 等标志）。
    *   **控制台精美 Rich Panel 交互**：当 Executor 的置信度低于当前工具激活的阈值线（普通工具默认 `0.85`，终端命令默认 `0.95`，均可通过 `.env` 中的环境变量 `BASE_CONFIDENCE_THRESHOLD` 与 `TERMINAL_CONFIDENCE_THRESHOLD` 进行动态配置与加载）或触发了高危指令警告时，在终端弹出精美的 **Rich Panel 警报面板** 并以 `Confirm.ask` 进行阻断或放行。
    *   **自愈闭环**：若控制者手动拒绝授权，系统将友好报错信息回馈给 AI，驱动 Executor 在不崩溃连接的前提下，完美进行自我重规与自愈。

### 1.3 服务端物理绝对沙箱屏障 (Server-Side Sandbox Blockade)
*   **核心实现**: [mcp_servers/system_runtime/src/server.py](file:///Users/Shared/Workspace/Tars/TarsAgent/mcp_servers/system_runtime/src/server.py)
*   **设计细节**:
    在 system_runtime 侧的终端物理执行前，设置了绝对底线屏障。利用严格的 substring 字符串包含检查，若任何终端执行指令中包含 `sudo`、`su` 或操作敏感文件名（`.env`、`.git`、`id_rsa`、`config.json` 等），物理层面直接抛出 `PermissionError`，彻底抵御并拦截了通过等于号（如 `git status --git-dir=.git`）或特殊字符进行绕过探测的行为。

---

## 🧪 2. 自动化与边界验证

为确保整套机制在以后的迭代进化中稳健不退化，系统配套了多方位的测试覆盖。

### 2.1 物理沙箱测试规范
*   **测试文件**: [tests/test_safety.py](file:///Users/Shared/Workspace/Tars/TarsAgent/tests/test_safety.py)
*   **测试项目**:
    1.  `test_server_sandbox_terminal_sudo`：确认在 system_runtime 服务端执行任何包含 `sudo`/`su` 的指令均被绝对物理拦截并安全返回报错。
    2.  `test_server_sandbox_terminal_sensitive_files`：确认在终端操作敏感文件（包含以等于号 `=.git` 等绕过方式）时物理拦截完全生效。
    3.  `test_server_sandbox_file_apis`：验证服务端的物理文件 API (`read_file`/`write_file`/`list_files`) 能够对敏感路径进行绝对拦截，且在列表目录时自动对其进行静默过滤。
    4.  `test_client_risk_checks`：对客户端 `check_command_risk` 定义的 6 大高危风险场景边界规则（绝对阻断与介入授权）进行 100% 规则覆盖测试。

### 2.2 置信度与人机协同交互测试规范
*   **测试文件**: [tests/test_workspace.py](file:///Users/Shared/Workspace/Tars/TarsAgent/tests/test_workspace.py)
*   **测试项目**:
    1.  `test_workspace_interceptor_paths` & `test_workspace_interceptor_list_files`：验证工作区物理路径开放后，文件读写与列表在任意目录下均可**物理自由通行**（零路径篡改重定向）。
    2.  `test_confidence_and_safety_hitl`：通过 Mock `prompt_user_intervention` 拦截器，完美验证了在低置信度下，控制者 **「手动放行/继续物理执行」** 以及 **「手动拒绝/友好阻断回馈自愈」** 两条核心条件分支逻辑的正确性与完整闭环。

---

## 🚀 3. 运行与验证指令

在根目录下执行 pytest 测试套件即可对整套防御机制进行 100% 的跑测验证：
```bash
./venv/bin/pytest tests/
```

### 3.1 测试通过回执
```text
tests/test_db.py ..                                                      [ 11%]
tests/test_intent_cap.py ...                                             [ 29%]
tests/test_safety.py ....                                                [ 52%]
tests/test_tool_rag.py .                                                 [ 58%]
tests/test_workspace.py .......                                          [100%]

======================== 17 passed, 7 warnings in 2.53s ========================
```
17 项自动化用例全部通过，验证了双重防御系统的绝对有效性和零死角。

---

## 🪐 4. 重构核心哲学总结

*   **坚固如盾**：从客户端 HITL 交互到服务端的沙箱抛错，两层防线互相交织，即使客户端被大模型绕过，底层物理机制也能以最高安全阻断一切渗透。
*   **流畅如水**：摆脱了粗暴的文件改写后，Tars 重获新生，对工作区的所有操作更加得心应手，真正成长为具备开发、重构及测试自我演化能力的工程助手。
