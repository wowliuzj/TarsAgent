import os
import json
import uuid
import asyncio
from typing import List, Dict, Any, Optional, Type
from datetime import datetime
from pydantic import BaseModel

from app.logger import logger
from app.mcp.client_manager import MCPClientManager
from app.mcp.state import TarsState, Mission, Lane
from app.mcp.graph import TarsGraphBuilder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from litellm import completion
from app.prompts import BASE_SYSTEM_PROMPT, get_dynamic_project_context

class TarsAgent:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.model = os.getenv("MODEL_NAME")
        if not self.model:
            raise ValueError("错误: 未在环境变量中找到 MODEL_NAME。")
        
        self.mcp_manager = MCPClientManager()
        self._mcp_initialized = False
        
        # 初始化编译后的图
        self.graph = TarsGraphBuilder(self).compile()
        logger.info("Tars 2.0 (LangGraph + THP) 引擎已就绪。")

    async def _init_mcp(self):
        """初始化并发现 MCP Servers (懒加载模式)"""
        if not self._mcp_initialized:
            await self.mcp_manager.start()
            self._mcp_initialized = True

    async def run(self, user_input: str) -> str:
        """执行 Tars 2.0 任务流"""
        await self._init_mcp()
        
        # 获取动态项目上下文
        dynamic_context = get_dynamic_project_context()
        
        # 1. 构造初始状态 (THP 规范)
        initial_state: TarsState = {
            "mission": Mission(
                id=str(uuid.uuid4()),
                goal=user_input
            ),
            "history": [
                SystemMessage(content=BASE_SYSTEM_PROMPT + dynamic_context),
                HumanMessage(content=user_input)
            ],
            "shared_memory": {},
            "task_pool": [],
            "audit_log": [],
            "current_lane": Lane.EXECUTION,
            "next_step": None,
            "current_task_index": 0,
            "executor_retries": 0,
            "planner_retries": 0,
            "audit_feedback": ""
        }

        logger.info(f"🚀 启动任务泳道: {initial_state['current_lane']}")
        
        # 2. 调用图引擎 (自动处理 ReAct 循环)
        final_state = await self.graph.ainvoke(initial_state)
        
        # 3. 提取最终回答
        final_response = "未能获取到回答。"
        for msg in reversed(final_state["history"]):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                final_response = msg.content
                break
        
        return final_response

    async def _call_model(
        self,
        messages: List[BaseMessage],
        use_tools: bool = True,
        response_format: Optional[Type[BaseModel]] = None
    ) -> AIMessage:
        """适配 LiteLLM 调用并返回 AIMessage"""
        llm_messages = []
        for m in messages:
            role = "user"
            if isinstance(m, SystemMessage): role = "system"
            elif isinstance(m, AIMessage): role = "assistant"
            elif isinstance(m, HumanMessage): role = "user"
            elif hasattr(m, "tool_call_id"): role = "tool"
            
            msg_dict = {"role": role, "content": str(m.content) if m.content else ""}
            
            # 处理 Assistant 的工具调用
            if role == "assistant" and isinstance(m, AIMessage) and m.tool_calls:
                llm_tool_calls = []
                for tc in m.tool_calls:
                    llm_tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"])
                        }
                    })
                msg_dict["tool_calls"] = llm_tool_calls
            
            # 处理 Tool 消息的响应
            if role == "tool":
                msg_dict["tool_call_id"] = m.tool_call_id
                # 注意：LiteLLM 的 tool 角色也需要 name
                msg_dict["name"] = getattr(m, "name", "tool")
            
            llm_messages.append(msg_dict)

        # 调用 LiteLLM
        tools = self.mcp_manager.all_tools if (self.mcp_manager.all_tools and use_tools) else None
        
        completion_kwargs = {
            "model": self.model,
            "messages": llm_messages,
            "tools": tools
        }
        if response_format:
            completion_kwargs["response_format"] = response_format

        response = await asyncio.to_thread(
            completion,
            **completion_kwargs
        )

        resp_msg = response.choices[0].message
        
        # 构造 AIMessage
        tool_calls = []
        if hasattr(resp_msg, "tool_calls") and resp_msg.tool_calls:
            for tc in resp_msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments)
                })
        
        return AIMessage(content=resp_msg.content or "", tool_calls=tool_calls)

    async def shutdown(self):
        """关闭所有 MCP 连接"""
        await self.mcp_manager.stop()
