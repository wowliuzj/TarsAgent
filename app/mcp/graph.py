import os
import json
from typing import Dict, List, Any, Union
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from app.mcp.state import TarsState, Lane, SubTask
from app.logger import logger
from app.prompts import PLANNER_PROMPT, AUDITOR_PROMPT, BASE_SYSTEM_PROMPT, get_dynamic_project_context

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
            
        response = await self.agent._call_model(messages, use_tools=False)
        plan_text = response.content
        logger.info(f"[*] Planner 制定的计划:\n{plan_text}")
        
        # 解析子任务列表 (Markdown 数字列表并提取精确度等级)
        import re
        steps = re.findall(r"^\d+\.\s*(.+)$", plan_text, re.MULTILINE)
        if not steps:
            # 兼容性降级：按换行切分并过滤空行
            steps = [line.strip() for line in plan_text.split("\n") if line.strip()]
            
        task_pool = []
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
        
        return {
            "task_pool": task_pool,
            "history": [SystemMessage(content=f"【当前任务计划 (由 Planner 制定)】\n{plan_text}")],
            "planner_retries": state.get("planner_retries", 0) + 1,
            "executor_retries": 0, # 重置执行者重试次数
            "audit_feedback": ""   # 清空反馈
        }

    async def think_node(self, state: TarsState) -> Dict[str, Any]:
        """执行者决策节点"""
        logger.info("--- [NODE: THINK (Executor)] ---")
        
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
            f"\n【IDAP 级别执行指南】:\n"
            f"{guideline}\n"
            f"\n【核心执行指导】:\n"
            f"你当前唯一的任务就是调用 MCP 工具完成上面的 <current_step>。如果工具调用成功并获取到核心数据，请以极其简练的纯事实陈述/JSON 格式总结此步骤的产出并直接输出。切记，严格遵守“非对话契约”，禁止闲聊或输出引导下一步的客套话。完成此步后，系统会自动推动到下一步。"
        )
        messages.append(SystemMessage(content=executor_system_prompt))
        
        # 5. Extract local ReAct message history belonging ONLY to the current step using retroactive scan
        local_react_messages = []
        for msg in reversed(state["history"]):
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
            
        return {"history": [response]}

    async def tool_node(self, state: TarsState) -> Dict[str, Any]:
        """物理执行节点"""
        logger.info("--- [NODE: EXECUTE_TOOLS] ---")
        last_message = state["history"][-1]
        
        tool_outputs = []
        if last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = dict(tool_call["args"])  # Copy args to allow modification
                logger.info(f"[*] MCP 调用: {tool_name}({args})")
                
                # --- 工作区隔离路径拦截与安全重定向 ---
                redirected_msg = ""
                
                # 1. 针对 read_file/write_file 进行路径参数过滤与修正
                if tool_name in ["write_file", "read_file"] and "file_path" in args:
                    path_val = args["file_path"]
                    allowed_coding_dirs = [
                        "app/", "mcp_servers/", "docs/", ".env", 
                        "TARS.md", "SOUL.md", "requirements.txt", 
                        "TODO.md", "Dockerfile", "docker-compose.yml",
                        "README.md", "CHANGELOG.md"
                    ]
                    # 如果不是在允许的代码维护路径下，且不以 data/workspace/ 开头
                    is_coding_task = any(path_val.startswith(d) for d in allowed_coding_dirs) or path_val in allowed_coding_dirs
                    
                    if not is_coding_task and not path_val.startswith("data/workspace/"):
                        import os
                        filename = os.path.basename(path_val)
                        new_path = f"data/workspace/{filename}"
                        args["file_path"] = new_path
                        logger.warning(f"⚠️ [工作区拦截器] 拦截到违规路径 '{path_val}'，已自动安全重定向至安全工作区: '{new_path}'")
                        redirected_msg = f"【安全提醒：由于路径合规规范限制，文件已自动安全重定向保存至 '{new_path}'。请你在此后的执行与陈述中均采用此重定向后的新路径。】\n"
                
                # 2. 针对 list_files 进行路径修正
                elif tool_name == "list_files" and "directory" in args:
                    dir_val = args["directory"]
                    allowed_coding_dirs = [
                        "app", "mcp_servers", "docs", "data/workspace"
                    ]
                    is_coding_task = any(dir_val.startswith(d) for d in allowed_coding_dirs) or dir_val in allowed_coding_dirs or dir_val == "."
                    if not is_coding_task:
                        args["directory"] = "data/workspace"
                        logger.warning(f"⚠️ [工作区拦截器] 拦截到违规目录列表请求 '{dir_val}'，已自动重定向至安全工作区: 'data/workspace'")
                        redirected_msg = "【安全提醒：由于路径合规规范限制，目录已自动重定向定位至 'data/workspace'。】\n"

                # 调用 MCP Manager
                result = await self.agent.mcp_manager.call_tool(tool_name, args)
                
                if redirected_msg:
                    result = redirected_msg + result
                
                tool_outputs.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=result
                ))
        
        return {"history": tool_outputs}

    async def register_step_node(self, state: TarsState) -> Dict[str, Any]:
        """登记当前步骤结果，进行事实蒸馏并推进指针"""
        idx = state.get("current_task_index", 0)
        task_pool = list(state.get("task_pool", []))
        if not task_pool:
            return {}
            
        last_msg = state["history"][-1]
        
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
        
        return {
            "task_pool": task_pool,
            "shared_memory": shared_memory,
            "current_task_index": next_idx
        }

    async def auditor_node(self, state: TarsState) -> Dict[str, Any]:
        """质量审计节点"""
        logger.info("--- [NODE: AUDITOR] ---")
        
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
            f"请审查以上结果。审查时，你必须根据每个子任务计划标题旁边的 [Level: LX] 标签，严格对照系统注入的分级审计准则进行判定。若完全符合该精确度级别的合规条件，请回复 'approved'；若需要驳回，请回复 'rejected'，然后换行写明具体驳回理由。"
        )
        
        dynamic_context = get_dynamic_project_context()
        messages = [
            SystemMessage(content=AUDITOR_PROMPT + dynamic_context),
            HumanMessage(content=audit_content)
        ]
        
        response = await self.agent._call_model(messages, use_tools=False)
        raw_verdict = response.content.strip()
        verdict = raw_verdict.lower()
        
        # Strip potential common prefixes injected by project S.O.P (like TARS.md)
        prefix = "【tars 收到您的指令，执行中...】"
        if verdict.startswith(prefix):
            verdict = verdict[len(prefix):].strip()
            
        is_approved = verdict.startswith("approved")
        reason = raw_verdict if not is_approved else ""
        
        logger.info(f"[*] 审计结果: {'✅ 通过' if is_approved else '❌ 驳回'}")
        if not is_approved:
            logger.warning(f"[*] 驳回理由: {reason}")
            
        return {
            "audit_feedback": reason if not is_approved else "",
            "executor_retries": state.get("executor_retries", 0) + (1 if not is_approved else 0),
            "current_task_index": 0 if not is_approved else state["current_task_index"] # Rejection resets index to 0
        }

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
        
        # 2. 调用 LLM 进行完美整合
        synthesis_prompt = (
            f"你现在的身份是 Tars Agent。所有子任务已经成功执行并通过审计。\n"
            f"你的任务是基于以下每个子任务的具体执行事实，为用户生成一份逻辑严密、排版美观、信息极其完整的最终报告。\n"
            f"【用户的原始需求】：\n"
            f"{state['mission'].goal}\n\n"
            f"【各个子任务的执行事实数据】：\n"
            f"{all_facts}\n\n"
            f"【要求】：\n"
            f"1. 严格遵守“非对话契约”，禁止输出任何闲聊、问候、交互式引导或下一步行动建议。你的回答就是最终要给用户的成果报告。\n"
            f"2. 最终回复的第一句必须以“【Tars 收到您的指令，执行中...】”开头。\n"
            f"3. 保持专业性，结构化排版，把所有步骤的核心事实整合到一份排版精致的最终 Markdown 报告中。"
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
