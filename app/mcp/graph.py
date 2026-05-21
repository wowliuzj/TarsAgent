import os
import json
import re
import shlex
import subprocess
from typing import Dict, List, Any, Union
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage, BaseMessage
from app.mcp.state import TarsState, Lane, SubTask, PlannerOutput, ExecutorThought, AuditorVerdict
from app.logger import logger
from app.prompts import PLANNER_PROMPT, AUDITOR_PROMPT, BASE_SYSTEM_PROMPT, get_dynamic_project_context
from rich.panel import Panel
from rich.prompt import Confirm
from app.shared_console import console

def verify_state_invariants(node_name: str, state: TarsState, is_post: bool = False):
    """
    状态不变式(Invariants)验证器。
    在每个节点执行前后校验状态一致性、数据结构正确性以及安全性规范。
    """
    phase = "Post" if is_post else "Pre"
    logger.debug(f"[THP Invariant Check] {phase}-{node_name}")
    
    # 基础校验：mission 结构永远不能丢失
    if "mission" not in state or not state["mission"]:
        raise AssertionError("THP Invariant Violate: 'mission' is required in TarsState")
    if not state["mission"].goal:
        raise AssertionError("THP Invariant Violate: 'mission.goal' cannot be empty")
        
    if node_name == "planner":
        if is_post:
            if "task_pool" not in state or not state["task_pool"]:
                raise AssertionError("THP Invariant Violate: Planner node must populate 'task_pool'")
            for task in state["task_pool"]:
                if not task.description:
                    raise AssertionError("THP Invariant Violate: SubTask description cannot be empty")
                if task.precision_level not in ["L1", "L2", "L3", "L4", "L5", "L6"]:
                    raise AssertionError(f"THP Invariant Violate: Invalid SubTask precision level '{task.precision_level}'")
                    
    elif node_name == "think":
        if not is_post:
            idx = state.get("current_task_index", 0)
            task_pool = state.get("task_pool", [])
            if not task_pool:
                raise AssertionError("THP Invariant Violate: Executor 'think' node requires a non-empty 'task_pool'")
            if idx < 0 or idx >= len(task_pool):
                raise AssertionError(f"THP Invariant Violate: Executor 'current_task_index' ({idx}) is out of bounds")
                
    elif node_name == "execute_tools":
        if not is_post:
            if not state.get("history"):
                raise AssertionError("THP Invariant Violate: execute_tools requires non-empty 'history'")
            last = state["history"][-1]
            if not isinstance(last, AIMessage) or not getattr(last, "tool_calls", None):
                raise AssertionError("THP Invariant Violate: execute_tools requires last message to contain tool_calls")
        if is_post:
            if not state["history"]:
                raise AssertionError("THP Invariant Violate: 'history' cannot be empty after execute_tools")
            if not isinstance(state["history"][-1], ToolMessage):
                raise AssertionError("THP Invariant Violate: execute_tools post-state must append ToolMessage outputs")

    elif node_name == "register_step":
        if not is_post:
            task_pool = state.get("task_pool", [])
            if not task_pool:
                raise AssertionError("THP Invariant Violate: register_step requires non-empty 'task_pool'")
            idx = state.get("current_task_index", 0)
            if idx < 0 or idx >= len(task_pool):
                raise AssertionError(f"THP Invariant Violate: register_step index ({idx}) is out of bounds")
            if not state.get("history"):
                raise AssertionError("THP Invariant Violate: register_step requires non-empty 'history'")
        else:
            if state.get("current_task_index", 0) < 0:
                raise AssertionError("THP Invariant Violate: register_step cannot produce negative index")
                
    elif node_name == "auditor":
        if is_post:
            if state.get("audit_feedback"):
                if state.get("executor_retries", 0) < 0:
                    raise AssertionError("THP Incorporate: Rejections must track positive retries")

def prune_history_messages(history: List[BaseMessage], max_chars: int = 25000) -> List[BaseMessage]:
    """
    智能历史消息修剪器 (HistoryPruner)。
    当历史记录过大时，对已完成步骤的巨大工具输出进行截断或浓缩，
    只保留最近的消息和关键系统提示，防止撑爆 LLM 视界。
    """
    total_len = sum(len(str(m.content)) for m in history if m.content)
    if total_len <= max_chars:
        return history
        
    logger.warning(f"🛡️ [HistoryPruner] 历史消息字符数 ({total_len}) 超过上限 ({max_chars})，启动智能修剪...")
    
    pruned = []
    if len(history) >= 2:
        pruned.extend(history[:2])
        remaining = history[2:]
    else:
        remaining = history
        
    keep_recent_count = 8
    recent_messages = remaining[-keep_recent_count:] if len(remaining) > keep_recent_count else remaining
    old_messages = remaining[:-keep_recent_count] if len(remaining) > keep_recent_count else []
    
    for msg in old_messages:
        if isinstance(msg, ToolMessage):
            if len(str(msg.content)) > 200:
                short_content = str(msg.content)[:150] + f"...[修剪器截断：该历史工具输出已被安全压缩，共 {len(str(msg.content))} 字符]..."
                pruned.append(ToolMessage(content=short_content, tool_call_id=msg.tool_call_id))
            else:
                pruned.append(msg)
        else:
            pruned.append(msg)
            
    pruned.extend(recent_messages)
    
    new_len = sum(len(str(m.content)) for m in pruned if m.content)
    logger.info(f"🛡️ [HistoryPruner] 修剪完成。历史消息字符数由 {total_len} 降至 {new_len}")
    return pruned

def check_command_risk(command: str) -> tuple[bool, bool, str]:
    """
    检查终端命令是否包含绝对阻断或需要人机确认的高危行为。
    返回: (is_blocked, is_warning, reason)
    """
    cmd_lower = command.lower()
    
    # 1. 越权提升 (绝对阻断)
    if re.search(r"\b(sudo|su)\b", command):
        return True, False, "检测到特权提升指令 (sudo/su)，绝对禁止执行！"
        
    # 2. 敏感文件探测/泄露 (绝对阻断)
    sensitive_patterns = [".env", ".git", "id_rsa", "config.json"]
    for sf in sensitive_patterns:
        if sf in command:
            return True, False, f"检测到对敏感文件/目录 '{sf}' 的操作，绝对禁止执行！"
            
    # 3. 反弹后门与安全外壳 (绝对阻断)
    if "/dev/tcp" in cmd_lower or "nc -l" in cmd_lower or "netcat" in cmd_lower:
        return True, False, "检测到反弹/后门监听命令，绝对禁止执行！"
        
    # 4. 毁灭性删除 (人机确认授权，若删除核心代码目录则绝对阻断)
    if "rm " in command or "rmdir " in command:
        if re.search(r"\brm\s+-[a-zA-Z]*[rfRF]\b", command) or "--recursive" in command or "-rf" in command or "-fr" in command:
            # 检查是否试图删除核心目录
            core_dirs = ["app", "mcp_servers", "tests", "docs", "TARS.md", "SOUL.md"]
            for d in core_dirs:
                if re.search(rf"\b{re.escape(d)}\b", command) or rf"/{d}" in command:
                    return True, False, f"检测到尝试毁灭性删除核心代码或骨架目录 '{d}'，绝对禁止执行！"
            return False, True, "检测到带有递归或强制删除标志的删除命令 (rm -rf/rm -r)，具有高破坏性！"
            
    # 5. 权限强改 (人机确认授权)
    if re.search(r"\b(chmod|chown|chgrp)\b", command):
        return False, True, "检测到尝试修改文件所有权或访问权限的指令 (chmod/chown/chgrp)！"
        
    # 6. 敏感数据外传 (人机确认授权)
    if "curl" in cmd_lower or "wget" in cmd_lower:
        if re.search(r"\b(curl|wget)\b.*(-[fF]|--post-file|--data|--form)\b", cmd_lower):
            return False, True, "检测到可能外传本地敏感数据的网络请求 (curl/wget with POST/Form flags)！"
            
    return False, False, ""

def parse_confidence(content: str) -> float:
    """
    从 Executor 思考的 thought 文本中解析自评自信度得分。
    """
    if not content:
        return 0.75  # 未匹配到时默认 0.75
        
    content_stripped = content.strip()
    # 尝试 JSON 解析 (THP 2.0)
    try:
        # LiteLLM/LLMs might wrap JSON in ```json ... ``` blocks
        json_str = content_stripped
        if "```json" in content_stripped:
            match_json = re.search(r"```json\s*(\{.*?\})\s*```", content_stripped, re.DOTALL)
            if match_json:
                json_str = match_json.group(1)
        elif content_stripped.startswith("`") or content_stripped.endswith("`"):
            json_str = content_stripped.strip("`").strip()
            
        thought = ExecutorThought.model_validate_json(json_str)
        return thought.confidence
    except Exception:
        pass
        
    # 兼容性降级：正则匹配 (THP 1.0)
    match = re.search(r"(?:Confidence|置信度|自信度)[:：]\s*(0?\.\d+|1\.0|1)", content, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
            
    return 0.75

def prompt_user_intervention(tool_name: str, args: dict, confidence: float, threshold: float, warning_reason: str = "") -> bool:
    """
    在控制台打印精美的 Rich Panel 警告，并使用 Confirm.ask 确认。
    返回 True 表示批准，False 表示拒绝。
    """
    import app.shared_console as shared_console
    
    # 暂停活跃的控制台 Spinner，以便于干净、无冲突地显示交互提示并读取输入
    status_to_resume = None
    if shared_console.active_status:
        status_to_resume = shared_console.active_status
        try:
            status_to_resume.stop()
        except Exception:
            pass

    title = "[bold red]⚠️  Tars 安全与置信度人机协同介入 (HITL Interceptor)[/bold red]"
    
    content_lines = []
    if warning_reason:
        content_lines.append(f"[bold yellow]警告原因[/bold yellow]: {warning_reason}")
    else:
        content_lines.append(f"[bold yellow]警告原因[/bold yellow]: AI 执行此动作的自信度评分低于系统安全线")
        
    content_lines.append(f"[bold]调用工具[/bold]: [cyan]{tool_name}[/cyan]")
    content_lines.append(f"[bold]工具参数[/bold]: {json.dumps(args, ensure_ascii=False, indent=2)}")
    content_lines.append(f"[bold]当前置信度[/bold]: [bold red]{confidence:.2f}[/bold red] (安全阈值: [green]{threshold:.2f}[/green])")
    content_lines.append("")
    content_lines.append("[dim]提示: 拒绝此动作后，系统会安全回馈报错给 AI，AI 将会自我修正并换用其他安全路径。[/dim]")
    
    panel = Panel(
        "\n".join(content_lines),
        title=title,
        border_style="yellow",
        expand=False
    )
    
    console.print("\n")
    console.print(panel)
    
    try:
        approved = Confirm.ask("[bold yellow]你是否授权执行此操作？[/bold yellow]", default=False)
        return approved
    except Exception as e:
        logger.error(f"HITL 交互异常: {e}")
        return False
    finally:
        # 恢复控制台 Spinner，继续背景思考流程
        if status_to_resume:
            try:
                status_to_resume.start()
            except Exception:
                pass

class TarsGraphBuilder:
    def __init__(self, agent_instance):
        """
        agent_instance: TarsAgent 的实例，用于复用其模型调用和 MCP 管理能力
        """
        self.agent = agent_instance
        self.workflow = StateGraph(TarsState)
        self._build_graph()

    def _build_graph(self):
        # 添加节点
        self.workflow.add_node("planner", self.planner_node)
        self.workflow.add_node("think", self.think_node) # Executor
        self.workflow.add_node("execute_tools", self.tool_node)
        self.workflow.add_node("register_step", self.register_step_node)
        self.workflow.add_node("auditor", self.auditor_node)
        self.workflow.add_node("reflect", self.reflect_node)

        # 设置入口 -> Planner
        self.workflow.add_edge(START, "planner")

        # Planner -> Executor (Think)
        self.workflow.add_edge("planner", "think")

        # Executor -> Tools 或 登记节点
        self.workflow.add_conditional_edges(
            "think",
            self.route_after_think,
            {
                "execute_tools": "execute_tools",
                "register_step": "register_step"
            }
        )

        # 工具执行完后回到思考节点
        self.workflow.add_edge("execute_tools", "think")
        
        # 登记节点 -> 思考节点(下一步) 或 审计节点(已全部跑完)
        self.workflow.add_conditional_edges(
            "register_step",
            self.route_after_register,
            {
                "think": "think",
                "auditor": "auditor"
            }
        )
        
        # Auditor -> 根据结果重试或结束
        self.workflow.add_conditional_edges(
            "auditor",
            self.route_after_auditor,
            {
                "reflect": "reflect",
                "think": "think",
                "planner": "planner"
            }
        )
        
        # 反思完后结束
        self.workflow.add_edge("reflect", END)

    async def planner_node(self, state: TarsState) -> Dict[str, Any]:
        """项目经理节点：负责任务拆解"""
        logger.info("--- [NODE: PLANNER] ---")
        verify_state_invariants("planner", state, is_post=False)
        
        dynamic_context = get_dynamic_project_context()
        
        # 通过 Tool RAG 动态获取当前 Query 最相关的工具
        tools = await self.agent.mcp_manager.get_tools_for_query(state["mission"].goal)
        tools_desc = ""
        if tools:
            tools_desc = "\n\n<available_tools>\n【注意：以下是当前系统可用且适合本次任务的 MCP 工具/技能定义。在制定计划步骤时，请尽量引导 Executor 使用这些特定工具，而不是设计通用的终端命令或 API URL】\n"
            for t in tools:
                func = t.get("function", {})
                tools_desc += f"- 工具名: `{func.get('name')}`\n"
                tools_desc += f"  描述: {func.get('description')}\n"
                tools_desc += f"  参数定义: {json.dumps(func.get('parameters', {}), ensure_ascii=False)}\n\n"
            tools_desc += "</available_tools>\n"
            
        messages = [
            SystemMessage(content=PLANNER_PROMPT + dynamic_context + tools_desc),
            HumanMessage(content=state["mission"].goal)
        ]
        
        if state.get("audit_feedback"):
            logger.warning("Planner 正在根据 Auditor 意见重新规划...")
            messages.append(SystemMessage(content=f"前次计划执行失败，审计意见：{state['audit_feedback']}。请重新规划。"))
            
        response = await self.agent._call_model(messages, use_tools=False, response_format=PlannerOutput)
        plan_text = response.content
        logger.info(f"[*] Planner 制定的计划:\n{plan_text}")
        
        task_pool = []
        try:
            planner_output = PlannerOutput.model_validate_json(plan_text)
            task_pool = planner_output.subtasks
            for idx, task in enumerate(task_pool):
                if not task.id:
                    task.id = f"task_{idx+1}"
        except Exception as e:
            logger.error(f"解析 Planner 结构化输出失败: {e}，尝试使用备用文本正则解析。")
            steps = re.findall(r"^\d+\.\s*(.+)$", plan_text, re.MULTILINE)
            if not steps:
                steps = [line.strip() for line in plan_text.split("\n") if line.strip()]
                
            for i, step in enumerate(steps):
                precision_match = re.search(r"\((L[1-6])\)\s*$", step)
                if precision_match:
                    precision_level = precision_match.group(1)
                    clean_desc = step[:precision_match.start()].strip()
                else:
                    precision_level = "L3"
                    clean_desc = step.strip()
                    
                task_pool.append(SubTask(
                    id=f"task_{i+1}",
                    description=clean_desc,
                    status="pending",
                    precision_level=precision_level
                ))
            
        logger.info(f"[*] 成功解析出 {len(task_pool)} 个子任务步骤。")
        
        result = {
            "task_pool": task_pool,
            "history": [SystemMessage(content=f"【当前任务计划 (由 Planner 制定)】\n{plan_text}")],
            "planner_retries": state.get("planner_retries", 0) + 1,
            "executor_retries": 0, # 重置执行者重试次数
            "audit_feedback": ""   # 清空反馈
        }
        
        test_state = state.copy()
        test_state.update(result)
        verify_state_invariants("planner", test_state, is_post=True)
        
        return result

    async def think_node(self, state: TarsState) -> Dict[str, Any]:
        """执行者决策节点"""
        logger.info("--- [NODE: THINK (Executor)] ---")
        verify_state_invariants("think", state, is_post=False)
        
        idx = state.get("current_task_index", 0)
        task_pool = state.get("task_pool", [])
        if not task_pool:
            task_pool = [SubTask(id="task_1", description=state["mission"].goal, status="pending")]
            
        if idx >= len(task_pool):
            idx = len(task_pool) - 1
            
        messages = []
        
        # 1. Base System Prompt + Dynamic project context
        dynamic_context = get_dynamic_project_context()
        messages.append(SystemMessage(content=BASE_SYSTEM_PROMPT + dynamic_context))
        
        # 2. User original goal
        messages.append(HumanMessage(content=state["mission"].goal))
        
        # 3. Previous step results from shared memory
        memory_context = ""
        if state.get("shared_memory"):
            memory_context = "\n".join([f"- {k}: {v}" for k, v in state["shared_memory"].items()])
            
        # 4. Current subtask and instructions
        current_task = task_pool[idx]
        
        # If there is audit feedback, inject it so Executor can remediate
        audit_context = ""
        if state.get("audit_feedback"):
            audit_context = f"\n\n<audit_feedback>\n【警告：前次审计被驳回，驳回理由为：】\n{state['audit_feedback']}\n请在执行此步骤时针对性修正。\n</audit_feedback>\n"

        # L6 自愈反馈注入：让测试失败堆栈真正回流到下一轮 Executor 推理上下文
        l6_heal_context = ""
        for msg in reversed(state["history"]):
            if isinstance(msg, SystemMessage) and "L6 Sandbox 自愈哨兵警告" in str(msg.content):
                l6_heal_context = (
                    "\n\n<l6_self_heal_feedback>\n"
                    f"{msg.content}\n"
                    "请优先根据上述测试失败日志修复当前步骤，再继续执行。\n"
                    "</l6_self_heal_feedback>\n"
                )
                break
            
        precision_guidelines = {
            "L1": "L1 (EXPLORATORY_CONCEPT - 概念探索级)：此步骤为概念性探索或创作。无需物理事实，允许发散创意。你被明确允许彻底旁路任何物理工具调用。如果你的常识或记忆已足够，请直接总结输出结论，绝对禁止发起任何无用或占位性的工具调用。",
            "L2": "L2 (MACRO_PLANNING - 宏观规划级)：此步骤为宏观规划。允许使用宏观经验概算，无需定位微观实体。你被明确允许彻底旁路任何物理工具调用。如果你的常识或记忆已足够，请直接总结输出结论，绝对禁止发起任何无意义的工具调用。",
            "L3": "L3 (FEASIBLE_PRACTICAL - 可行指导级 - 旅行规划的默认级)：此步骤为常规可行指南。推荐实体（如酒店、停靠地）必须真实存在，但细碎细节（如联系电话、波动价格）允许合理估计或提供“当天自查提示”。你被明确允许彻底旁路任何物理工具调用。如果你的常识或先前步骤记忆（shared_memory）已能给出答案，请直接总结输出结论，绝对禁止发起冗余、模拟或占位性的工具调用（如 dummy web search, echo 占位或写入无用临时文件）。",
            "L4": "L4 (RESEARCH_ANALYTICAL - 调研分析级)：此步骤为严肃行业调研。数据必须具备时效性并提供真实参考数值，不允许留空。你强制必须调用物理工具（Search API/API 查询等）对事实进行核对，绝对不允许依靠大脑常识进行无工具收敛旁路。",
            "L5": "L5 (FACTUAL_VERIFIED - 高保事实核查级)：此步骤为强事实核查。你必须提供 100% 绝对精确的事实性数据（如特定座机、精确气象与路况）。你强制必须调用物理工具（Search API/API 查询等）对事实发起物理核验，绝对不允许依靠常识或估计做无工具旁路。",
            "L6": "L6 (STRICT_TRANSACTIONAL - 严格事务级)：此步骤涉及代码、命令或数据库事务。你强制必须调用物理工具执行，并通过真实终端/系统回执验证结果，零容错。"
        }
        level = current_task.precision_level if hasattr(current_task, "precision_level") else "L3"
        guideline = precision_guidelines.get(level, precision_guidelines["L3"])

        executor_system_prompt = (
            f"<current_step>\n"
            f"当前子任务 ({idx + 1}/{len(task_pool)}):\n"
            f"【{current_task.description}】\n"
            f"精确度等级：[{level}]\n"
            f"</current_step>\n"
            f"\n<shared_memory>\n"
            f"前面步骤已收集的事实数据与共享上下文如下：\n"
            f"{memory_context or '（暂无前置步骤数据）'}\n"
            f"</shared_memory>\n"
            f"{audit_context}"
            f"{l6_heal_context}"
            f"\n【IDAP 级别执行指南】:\n"
            f"{guideline}\n"
            f"\n【核心执行指导】:\n"
            f"你当前唯一的任务就是调用 MCP 工具完成上面的 <current_step>。如果工具调用成功并获取到核心数据，请以极其简练的纯事实陈述/JSON 格式总结此步骤的产出并直接输出。切记，严格遵守“非对话契约”，禁止闲聊或输出引导下一步的客套话。完成此步后，系统会自动推动到下一步。"
        )
        messages.append(SystemMessage(content=executor_system_prompt))
        
        # 5. Extract local ReAct message history belonging ONLY to the current step using retroactive scan
        # 使用 HistoryPruner 智能剪裁大上下文历史
        pruned_history = prune_history_messages(state["history"])
        local_react_messages = []
        for msg in reversed(pruned_history):
            if isinstance(msg, ToolMessage):
                local_react_messages.insert(0, msg)
            elif isinstance(msg, AIMessage) and msg.tool_calls:
                local_react_messages.insert(0, msg)
            else:
                break
                
        messages.extend(local_react_messages)
        
        response = await self.agent._call_model(messages)
        
        # 如果 Executor 没有调用工具，而是直接输出回答，记录下来供审计排查
        if response.content and not response.tool_calls:
            logger.info(f"[*] Executor 的初步执行结果:\n{response.content}")
            
        result = {"history": [response]}
        test_state = state.copy()
        test_state["history"] = test_state["history"] + [response]
        verify_state_invariants("think", test_state, is_post=True)
        
        return result

    async def tool_node(self, state: TarsState) -> Dict[str, Any]:
        """物理执行节点"""
        logger.info("--- [NODE: EXECUTE_TOOLS] ---")
        verify_state_invariants("execute_tools", state, is_post=False)
        last_message = state["history"][-1]
        
        tool_outputs = []
        if last_message.tool_calls:
            # 解析 AI 思考中的自评置信度
            confidence = parse_confidence(last_message.content)
            logger.info(f"[*] AI 动作自评置信度得分: {confidence:.2f}")
            console.print(f"[bold cyan][*] AI 动作自评置信度得分: {confidence:.2f}[/bold cyan]")
            
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = dict(tool_call["args"])  # Copy args to allow modification
                logger.info(f"[*] MCP 调用: {tool_name}({args})")
                
                # 确定该工具的安全置信度阈值 (由环境变量动态配置)
                try:
                    base_threshold = float(os.environ["BASE_CONFIDENCE_THRESHOLD"])
                    terminal_threshold = float(os.environ["TERMINAL_CONFIDENCE_THRESHOLD"])
                except KeyError as e:
                    missing_key = str(e).strip("'")
                    logger.error(f"❌ 安全阻断: 缺失必要阈值配置 {missing_key}")
                    result = f"【安全阻断：系统缺失必要的安全阈值配置 `{missing_key}`。请先在 .env 中配置完整后再执行。】"
                    tool_outputs.append(ToolMessage(
                        tool_call_id=tool_call["id"],
                        content=result
                    ))
                    continue
                except ValueError:
                    logger.error("❌ 安全阻断: 安全阈值配置格式非法")
                    result = "【安全阻断：检测到 BASE_CONFIDENCE_THRESHOLD 或 TERMINAL_CONFIDENCE_THRESHOLD 格式非法，请修复 .env 后重试。】"
                    tool_outputs.append(ToolMessage(
                        tool_call_id=tool_call["id"],
                        content=result
                    ))
                    continue

                active_threshold = base_threshold
                if tool_name == "run_terminal_command":
                    active_threshold = terminal_threshold
                
                # 检查高危终端命令风险
                is_blocked = False
                is_warning = False
                reason = ""
                if tool_name == "run_terminal_command" and "command" in args:
                    is_blocked, is_warning, reason = check_command_risk(args["command"])
                
                # 双重纵深防御与人机协同介入决策逻辑
                if is_blocked:
                    logger.error(f"❌ 安全阻断: {reason}")
                    result = f"【安全阻断：该终端指令由于触发物理沙箱安全规则被绝对拦截。原因：{reason}】"
                elif is_warning or confidence < active_threshold:
                    warning_reason = reason if is_warning else f"AI 自评置信度 ({confidence:.2f}) 低于该工具的安全阈值线 ({active_threshold:.2f})"
                    logger.warning(f"⚠️ 触发人机协同介入确认: {warning_reason}")
                    
                    approved = prompt_user_intervention(
                        tool_name=tool_name,
                        args=args,
                        confidence=confidence,
                        threshold=active_threshold,
                        warning_reason=warning_reason
                    )
                    
                    if approved:
                        logger.info("✅ 用户手动授权通过，继续交付物理执行。")
                        result = await self.agent.mcp_manager.call_tool(tool_name, args)
                    else:
                        logger.warning("❌ 用户手动拒绝授权，拦截执行并触发 AI 自愈。")
                        result = f"【安全阻断：由于置信度过低或具有潜在破坏风险，人类控制者手动拒绝了此授权。原因：{warning_reason}。请你换用其他安全、高置信度或非破坏性的做法。】"
                else:
                    # 正常安全执行
                    result = await self.agent.mcp_manager.call_tool(tool_name, args)
                
                # 增加大模型上下文截断保护哨兵 (Tool Output Truncation Safeguard)
                # 保护阈值设为 50000 字符（约合 1.25 万 Tokens 左右），确保绝对不撑爆上下文视界
                MAX_TOOL_OUTPUT_CHARS = 50000
                if isinstance(result, str) and len(result) > MAX_TOOL_OUTPUT_CHARS:
                    original_len = len(result)
                    truncated_content = result[:MAX_TOOL_OUTPUT_CHARS]
                    result = (
                        f"【⚠️系统安全卫兵提醒：该工具返回的内容体积巨大（共 {original_len} 字符），已自动为您安全截断前 {MAX_TOOL_OUTPUT_CHARS} 字符以防大模型脑溢血崩溃。磁盘中的物理文件依然是完整未受损的。】\n\n"
                        f"{truncated_content}\n\n"
                        f"【...剩余 {original_len - MAX_TOOL_OUTPUT_CHARS} 字符已被系统安全自动截断...】"
                    )
                    logger.warning(f"🛡️ [截断保护哨兵] 成功拦截并截断了工具 '{tool_name}' 的巨量输出（从 {original_len} 字符截断至 {MAX_TOOL_OUTPUT_CHARS}）")
                
                tool_outputs.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=result
                ))
        
        result = {"history": tool_outputs}
        test_state = state.copy()
        test_state["history"] = test_state["history"] + tool_outputs
        verify_state_invariants("execute_tools", test_state, is_post=True)
        return result

    async def register_step_node(self, state: TarsState) -> Dict[str, Any]:
        """登记当前步骤结果，进行事实蒸馏并推进指针"""
        verify_state_invariants("register_step", state, is_post=False)
        idx = state.get("current_task_index", 0)
        task_pool = list(state.get("task_pool", []))
        if not task_pool:
            return {}
            
        last_msg = state["history"][-1]
        
        # 执行 L6 严格自检 (Sandbox Auto-Testing)
        level = task_pool[idx].precision_level if hasattr(task_pool[idx], "precision_level") else "L3"
        if level == "L6":
            logger.info("⚡ [L6 Sandbox] 触发 L6 严格事务级自检。正在自动拉起本地测试套件...")
            console.print("[bold yellow]⚡ [L6 Sandbox] 正在自动运行本地测试套件进行严格自检...[/bold yellow]")
            
            test_cmd = os.getenv("L6_SANDBOX_TEST_CMD", ".venv/bin/pytest -q")
            test_timeout = int(os.getenv("L6_SANDBOX_TEST_TIMEOUT", "60"))
                
            try:
                # 运行可配置测试命令（默认快速模式）
                process = subprocess.run(
                    shlex.split(test_cmd),
                    capture_output=True,
                    text=True,
                    timeout=test_timeout
                )
                if process.returncode != 0:
                    retries = state.get("executor_retries", 0)
                    max_retries = int(os.getenv("MAX_EXECUTOR_RETRIES", "3"))
                    
                    logger.warning(f"❌ [L6 Sandbox] 自检测试未通过 (已重试: {retries}/{max_retries})。")
                    console.print(f"[bold red]❌ [L6 Sandbox] 自检测试未通过 (已重试: {retries}/{max_retries})，已触发 AI 自我修复机制！[/bold red]")
                    
                    if retries < max_retries:
                        # 记录自愈反馈并退回 think 节点
                        feedback_msg = (
                            f"【⚡ L6 Sandbox 自愈哨兵警告】：此步骤产出的代码在运行本地测试套件时失败。\n"
                            f"【测试命令】：{test_cmd}\n"
                            f"【测试报错详情】：\n{process.stdout or process.stderr}\n"
                            f"请分析上述报错原因，并在此步骤下重新调用工具修正代码！"
                        )
                        return {
                            "history": [SystemMessage(content=feedback_msg)],
                            "executor_retries": retries + 1,
                            # 关键：我们不推过 current_task_index，使其维持在 idx
                            "current_task_index": idx
                        }
                    else:
                        logger.error("🚨 [L6 Sandbox] 自检测试失败且已达重试上限，将交给质量审计节点进一步裁决。")
                else:
                    logger.info("✅ [L6 Sandbox] 本地测试套件自检通过！")
                    console.print("[bold green]✅ [L6 Sandbox] 测试通过，代码自检 100% 绿色！[/bold green]")
            except Exception as test_err:
                logger.error(f"[L6 Sandbox] 执行测试套件发生异常: {test_err}")

        # 1. 记录此步骤的结果为 completed
        task_pool[idx] = SubTask(
            id=task_pool[idx].id,
            description=task_pool[idx].description,
            status="completed",
            result=last_msg.content
        )
        
        # 2. 蒸馏事实存入 shared_memory
        shared_memory = dict(state.get("shared_memory", {}))
        shared_memory[f"step_{idx+1}_result"] = last_msg.content
        
        # 3. 指针推进到下一步
        next_idx = idx + 1
        logger.info(f"✅ 子任务 {idx+1}/{len(task_pool)} 已执行完成。数据已沉淀到 shared_memory，推进指针至: {next_idx}")
        
        result = {
            "task_pool": task_pool,
            "shared_memory": shared_memory,
            "current_task_index": next_idx
        }
        test_state = state.copy()
        test_state.update(result)
        verify_state_invariants("register_step", test_state, is_post=True)
        return result

    async def auditor_node(self, state: TarsState) -> Dict[str, Any]:
        """质量审计节点"""
        logger.info("--- [NODE: AUDITOR] ---")
        verify_state_invariants("auditor", state, is_post=False)
        
        # 1. 汇总所有子任务步骤的执行结果作为审查内容
        plan_lines = []
        for i, subtask in enumerate(state.get("task_pool", [])):
            level = subtask.precision_level if hasattr(subtask, "precision_level") else "L3"
            plan_lines.append(f"{i+1}. {subtask.description} [Level: {level}]")
        plan_text = "\n".join(plan_lines) if plan_lines else "无明确计划"
        
        executor_results = []
        shared_mem = state.get("shared_memory", {})
        for i, subtask in enumerate(state.get("task_pool", [])):
            key = f"step_{i+1}_result"
            val = shared_mem.get(key, "未执行/无输出")
            level = subtask.precision_level if hasattr(subtask, "precision_level") else "L3"
            executor_results.append(f"### 子任务 {i+1} 计划: {subtask.description} [Level: {level}]\n执行结果:\n{val}")
        executor_final_results_text = "\n\n".join(executor_results)
        
        audit_content = (
            f"用户的原始需求: {state['mission'].goal}\n\n"
            f"Planner制定的完整计划:\n{plan_text}\n\n"
            f"Executor的完整执行结果:\n{executor_final_results_text}\n\n"
            f"请审查以上结果。审查时，你必须根据每个子任务计划标题旁边的 [Level: LX] 标签，严格对照系统注入的分级审计准则进行判定。若完全符合该精确度级别的合规条件，请输出 approved 状态的 JSON 对象；若需要驳回，请输出 rejected 状态并详细说明驳回理由。"
        )
        
        dynamic_context = get_dynamic_project_context()
        messages = [
            SystemMessage(content=AUDITOR_PROMPT + dynamic_context),
            HumanMessage(content=audit_content)
        ]
        
        response = await self.agent._call_model(messages, use_tools=False, response_format=AuditorVerdict)
        raw_verdict = response.content.strip()
        logger.info(f"[*] Auditor raw output: {raw_verdict}")
        
        try:
            verdict_obj = AuditorVerdict.model_validate_json(raw_verdict)
            is_approved = verdict_obj.verdict == "approved"
            reason = verdict_obj.reason or ""
        except Exception as e:
            logger.error(f"解析 Auditor 结构化输出失败: {e}，尝试使用备用文本解析。")
            verdict = raw_verdict.lower()
            prefix = "【tars 收到您的指令，执行中...】"
            if verdict.startswith(prefix):
                verdict = verdict[len(prefix):].strip()
                
            is_approved = verdict.startswith("approved")
            reason = raw_verdict if not is_approved else ""
        
        logger.info(f"[*] 审计结果: {'✅ 通过' if is_approved else '❌ 驳回'}")
        if not is_approved:
            logger.warning(f"[*] 驳回理由: {reason}")
            
        result = {
            "audit_feedback": reason if not is_approved else "",
            "executor_retries": state.get("executor_retries", 0) + (1 if not is_approved else 0),
            "current_task_index": 0 if not is_approved else state["current_task_index"] # Rejection resets index to 0
        }
        
        test_state = state.copy()
        test_state.update(result)
        verify_state_invariants("auditor", test_state, is_post=True)
        
        return result

    async def reflect_node(self, state: TarsState) -> Dict[str, Any]:
        """反思与记忆节点：在此节点对所有子任务的执行结果进行最终的聚合与提炼，生成完美的统一大文章作为最终回答"""
        logger.info("--- [NODE: REFLECT] ---")
        
        # 1. 汇总所有步骤的结果
        executor_results = []
        shared_mem = state.get("shared_memory", {})
        for i in range(len(state.get("task_pool", []))):
            key = f"step_{i+1}_result"
            val = shared_mem.get(key, "未执行/无输出")
            executor_results.append(f"### 步骤 {i+1}：{state['task_pool'][i].description}\n{val}")
        all_facts = "\n\n".join(executor_results)
        
        # 2. 检查是否为纯文本对话/简单问答通道
        # (只有 1 个子任务，且输出为非 JSON、不含技术 key 的纯文字直接回复)
        # 如果是，则绕过 LLM 整合合成，直接以最自然的形式返回给使用者，杜绝官僚形式的“最终报告”。
        step_1_val = shared_mem.get("step_1_result", "")
        
        # 尝试剥离 ExecutorThought 的 JSON 壳以获得实际的回复内容
        actual_val = step_1_val
        import json
        if isinstance(step_1_val, str) and step_1_val.strip().startswith("{"):
            try:
                data = json.loads(step_1_val)
                if isinstance(data, dict) and "reasoning" in data:
                    actual_val = data["reasoning"]
            except Exception:
                pass

        is_simple_chat = False
        if len(state.get("task_pool", [])) <= 1 and isinstance(actual_val, str) and actual_val.strip():
            actual_stripped = actual_val.strip()
            is_json = (actual_stripped.startswith("{") and actual_stripped.endswith("}")) or (actual_stripped.startswith("[") and actual_stripped.endswith("]"))
            has_tech_keys = any(k in actual_val for k in ['"stdout":', '"stderr":', '"status":', '"script_written":', '"saved_markdown_path":'])
            if not is_json and not has_tech_keys:
                is_simple_chat = True
                
        if is_simple_chat:
            final_content = actual_val.strip()
            prefix = "【Tars 收到您的指令，执行中...】"
            if not final_content.startswith(prefix):
                final_content = prefix + final_content
            
            logger.info("🛡️ [直接对话通道] 检测到纯文本问答/闲聊响应，直接返回 Executor 原生结果，旁路报告合成。")
            return {"history": [AIMessage(content=final_content)]}
        
        # 3. 调用 LLM 进行成果整理 (软化提示词，告别机械死板的内部审计报告格式，仅改变返回给使用者的信息)
        synthesis_prompt = (
            f"你现在的身份是 Tars Agent。所有子任务已经成功执行并通过审计。\n"
            f"你的任务是基于以下每个子任务的具体执行事实，为人类用户生成一个完美、精美且清晰的高质量最终任务成果呈现。\n"
            f"【用户的原始需求】：\n"
            f"{state['mission'].goal}\n\n"
            f"【各个子任务的执行事实数据】：\n"
            f"{all_facts}\n\n"
            f"【极其重要的要求】：\n"
            f"1. 严格遵守“非对话契约”，禁止输出任何闲聊、问候、交互式引导或下一步行动建议。你的回答就是最终要给用户的成果呈现。\n"
            f"2. 最终回复的第一句必须以“【Tars 收到您的指令，执行中...】”开头。\n"
            f"3. 成果导向呈现：请直接将任务的核心成果（例如：如果是抓取并转换后的 Markdown 文章，请直接将整篇高质量排版文章内容完整呈现给用户；如果是数据或表格查询，请直接给出精致的表格与分析数据）。\n"
            f"4. 绝对禁止以“最终审计报告”、“合规性检查”、“审计结果”、“步骤 1 步骤 2 列表”等面向内部系统调试的冰冷机械报告格式输出。用户的成果才是回答的主体！"
        )
        
        dynamic_context = get_dynamic_project_context()
        messages = [
            SystemMessage(content=BASE_SYSTEM_PROMPT + dynamic_context),
            HumanMessage(content=synthesis_prompt)
        ]
        
        response = await self.agent._call_model(messages, use_tools=False)
        
        # 将整合后的最终 AIMessage 追加到 history 中，供外部作为 final_response 提取
        return {"history": [response]}

    def route_after_think(self, state: TarsState) -> str:
        last_message = state["history"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "execute_tools"
        return "register_step"

    def route_after_register(self, state: TarsState) -> str:
        if state.get("current_task_index", 0) < len(state.get("task_pool", [])):
            return "think"
        return "auditor"

    def route_after_auditor(self, state: TarsState) -> str:
        if not state.get("audit_feedback"):
            return "reflect" # 审计通过
            
        max_executor_retries = int(os.getenv("MAX_EXECUTOR_RETRIES", "3"))
        max_planner_retries = int(os.getenv("MAX_PLANNER_RETRIES", "2"))
            
        executor_retries = state.get("executor_retries", 0)
        if executor_retries < max_executor_retries:
            logger.info(f"🔄 审计未通过，退回 Executor (已重试 {executor_retries}/{max_executor_retries} 次)")
            return "think"
            
        planner_retries = state.get("planner_retries", 0)
        if planner_retries < max_planner_retries:
            logger.warning(f"🔄 Executor 已达重试上限，退回 Planner 重新规划 (已重试 {planner_retries}/{max_planner_retries} 次)")
            return "planner"
            
        logger.error("🚨 任务彻底失败，已达所有重试上限。")
        return "reflect"

    def compile(self):
        return self.workflow.compile()
