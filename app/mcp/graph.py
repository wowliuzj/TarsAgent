import json
from typing import Dict, List, Any, Union
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.mcp.state import TarsState, Lane
from app.logger import logger

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
        self.workflow.add_node("think", self.think_node)
        self.workflow.add_node("execute_tools", self.tool_node)
        self.workflow.add_node("reflect", self.reflect_node)

        # 设置入口
        self.workflow.add_edge(START, "think")

        # 设置条件路由
        self.workflow.add_conditional_edges(
            "think",
            self.should_continue,
            {
                "continue": "execute_tools",
                "end": "reflect"
            }
        )

        # 工具执行完后回到思考节点
        self.workflow.add_edge("execute_tools", "think")
        
        # 反思完后结束
        self.workflow.add_edge("reflect", END)

    async def think_node(self, state: TarsState) -> Dict[str, Any]:
        """LLM 决策节点"""
        logger.info("--- [NODE: THINK] ---")
        # 调用模型 (复用 agent 现有的逻辑)
        # 注意：这里需要适配历史记录格式
        response = await self.agent._call_model(state["history"])
        
        # THP 规范：可以在这里加入 Post-check 逻辑
        return {"history": [response]}

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

    async def reflect_node(self, state: TarsState) -> Dict[str, Any]:
        """反思与记忆节点"""
        logger.info("--- [NODE: REFLECT] ---")
        # 如果需要反思并保存记忆，在这里调用 agent.memory_save 等逻辑
        # 暂时留空，后续扩展
        return {}

    def should_continue(self, state: TarsState) -> str:
        """路由逻辑：根据最后一条消息是否有 tool_calls 决定流向"""
        last_message = state["history"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "continue"
        return "end"

    def compile(self):
        return self.workflow.compile()
