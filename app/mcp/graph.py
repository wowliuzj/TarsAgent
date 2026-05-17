import os
import json
from typing import Dict, List, Any, Union
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from app.mcp.state import TarsState, Lane, SubTask
from app.logger import logger
from app.prompts import PLANNER_PROMPT, AUDITOR_PROMPT

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
        self.workflow.add_node("auditor", self.auditor_node)
        self.workflow.add_node("reflect", self.reflect_node)

        # 设置入口 -> Planner
        self.workflow.add_edge(START, "planner")

        # Planner -> Executor (Think)
        self.workflow.add_edge("planner", "think")

        # Executor -> Tools 或 Auditor
        self.workflow.add_conditional_edges(
            "think",
            self.route_after_think,
            {
                "execute_tools": "execute_tools",
                "auditor": "auditor"
            }
        )

        # 工具执行完后回到思考节点
        self.workflow.add_edge("execute_tools", "think")
        
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
        messages = [
            SystemMessage(content=PLANNER_PROMPT),
            HumanMessage(content=state["mission"].goal)
        ]
        
        if state.get("audit_feedback"):
            logger.warning("Planner 正在根据 Auditor 意见重新规划...")
            messages.append(SystemMessage(content=f"前次计划执行失败，审计意见：{state['audit_feedback']}。请重新规划。"))
            
        response = await self.agent._call_model(messages, use_tools=False)
        plan_text = response.content
        logger.info(f"[*] Planner 制定的计划:\n{plan_text}")
        
        return {
            "task_pool": [SubTask(id="plan_1", description=plan_text)],
            "history": [SystemMessage(content=f"【当前任务计划 (由 Planner 制定)】\n{plan_text}")],
            "planner_retries": state.get("planner_retries", 0) + 1,
            "executor_retries": 0, # 重置执行者重试次数
            "audit_feedback": ""   # 清空反馈
        }

    async def think_node(self, state: TarsState) -> Dict[str, Any]:
        """执行者决策节点"""
        logger.info("--- [NODE: THINK (Executor)] ---")
        messages = list(state["history"])
        
        # 如果是被 auditor 驳回的，且尚未重新执行，注入反馈
        if state.get("audit_feedback"):
            messages.append(SystemMessage(content=f"【审计员驳回】\n理由: {state['audit_feedback']}\n请根据驳回理由修正你的输出或重新调用工具。"))
            
        response = await self.agent._call_model(messages)
        
        # 如果被驳回后重新执行，清空 feedback 避免下个循环无限注入
        return {"history": [response], "audit_feedback": ""}

    async def tool_node(self, state: TarsState) -> Dict[str, Any]:
        """物理执行节点"""
        logger.info("--- [NODE: EXECUTE_TOOLS] ---")
        last_message = state["history"][-1]
        
        tool_outputs = []
        if last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = tool_call["args"]
                logger.info(f"[*] MCP 调用: {tool_name}({args})")
                
                # 调用 MCP Manager
                result = await self.agent.mcp_manager.call_tool(tool_name, args)
                
                tool_outputs.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=result
                ))
        
        return {"history": tool_outputs}

    async def auditor_node(self, state: TarsState) -> Dict[str, Any]:
        """质量审计节点"""
        logger.info("--- [NODE: AUDITOR] ---")
        
        executor_response = "无回答"
        for msg in reversed(state["history"]):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                executor_response = msg.content
                break
                
        plan_text = state["task_pool"][0].description if state.get("task_pool") else "无明确计划"
        
        audit_content = (
            f"用户的原始需求: {state['mission'].goal}\n"
            f"Planner制定的计划: {plan_text}\n"
            f"Executor的最终结果: {executor_response}\n\n"
            f"请审查以上结果。如果通过，请直接且仅回复 'approved'。如果驳回，请回复 'rejected'，然后换行说明具体理由。"
        )
        
        messages = [
            SystemMessage(content=AUDITOR_PROMPT),
            HumanMessage(content=audit_content)
        ]
        
        response = await self.agent._call_model(messages, use_tools=False)
        verdict = response.content.strip().lower()
        
        is_approved = verdict.startswith("approved")
        reason = response.content if not is_approved else ""
        
        logger.info(f"[*] 审计结果: {'✅ 通过' if is_approved else '❌ 驳回'}")
        if not is_approved:
            logger.warning(f"[*] 驳回理由: {reason}")
            
        return {
            "audit_feedback": reason if not is_approved else "",
            "executor_retries": state.get("executor_retries", 0) + (1 if not is_approved else 0)
        }

    async def reflect_node(self, state: TarsState) -> Dict[str, Any]:
        """反思与记忆节点"""
        logger.info("--- [NODE: REFLECT] ---")
        return {}

    def route_after_think(self, state: TarsState) -> str:
        last_message = state["history"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "execute_tools"
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
