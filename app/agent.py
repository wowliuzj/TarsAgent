import os
import json
import asyncio
from typing import List, Dict, Any, Optional
from litellm import acompletion # 使用异步版本
from app.db import engine, TarsMessage, TarsSession
from app.mcp.client_manager import MCPClientManager
from app.prompts import BASE_SYSTEM_PROMPT, MEMORY_CONTEXT_PROMPT, REFLECTION_PROMPT
from sqlmodel import Session, select
from rich.console import Console
from rich.panel import Panel

console = Console()

class TarsAgent:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.model = os.getenv("MODEL_NAME")
        if not self.model:
            raise ValueError("错误: 未在环境变量中找到 MODEL_NAME。")
        self.mcp_manager = MCPClientManager()
        self._mcp_initialized = False

    async def _init_mcp(self):
        """初始化并启动所有 MCP Servers"""
        if not self._mcp_initialized:
            await self.mcp_manager.start()
            self._mcp_initialized = True

    def _get_history(self) -> List[Dict[str, Any]]:
        """从数据库中检索当前会话的所有历史消息。"""
        with Session(engine) as session:
            statement = select(TarsMessage).where(TarsMessage.session_id == self.session_id).order_by(TarsMessage.created_at)
            results = session.exec(statement).all()
            
            history = [{"role": "system", "content": BASE_SYSTEM_PROMPT}]
            for msg in results:
                m = {"role": msg.role, "content": msg.content}
                if msg.tool_calls:
                    m["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    m["tool_call_id"] = msg.tool_call_id
                history.append(m)
            return history

    def _save_message(self, role: str, content: str = None, tool_calls: List = None, tool_call_id: str = None):
        """将消息持久化到数据库。"""
        serializable_tool_calls = None
        if tool_calls:
            serializable_tool_calls = []
            for tc in tool_calls:
                if hasattr(tc, "model_dump"):
                    serializable_tool_calls.append(tc.model_dump())
                elif hasattr(tc, "dict"):
                    serializable_tool_calls.append(tc.dict())
                else:
                    serializable_tool_calls.append(dict(tc))

        with Session(engine) as session:
            new_msg = TarsMessage(
                session_id=self.session_id,
                role=role,
                content=content,
                tool_calls=serializable_tool_calls,
                tool_call_id=tool_call_id
            )
            session.add(new_msg)
            session.commit()

    async def run(self, user_input: str) -> str:
        """运行异步 ReAct 循环，包含 MCP 调度、RAG 检索和自我反思"""
        
        # 1. 初始化 MCP
        await self._init_mcp()
        
        # 2. 保存用户输入
        self._save_message("user", user_input)
        
        # 3. 静默记忆检索 (RAG) - 通过 MCP 调用 system_runtime
        memory_data = ""
        try:
            memory_data = await self.mcp_manager.call_tool("memory_search", {"query": user_input, "top_k": 2})
        except:
            pass

        history = self._get_history()
        
        # 如果找回了相关记忆，将其注入到当前上下文
        if memory_data and "找回的相关记忆" in memory_data:
            memory_prompt = MEMORY_CONTEXT_PROMPT.format(memory_content=memory_data)
            history.insert(1, {"role": "system", "content": memory_prompt})

        # 4. 主 ReAct 循环
        max_steps = int(os.getenv("MAX_STEPS", 20))
        step = 0
        final_answer = "未能在限步内完成任务。"
        
        while step < max_steps:
            step += 1
            console.print(f"\n[bold cyan]>>> Step {step}[/bold cyan] | 正在通过 MCP 调度工具 | 模型: {self.model} ...")
            
            # 确保在没有任何工具时传入 None，防止 API 报错
            tools = self.mcp_manager.all_tools if self.mcp_manager.all_tools else None
            
            # 使用异步 completion
            response = await acompletion(
                model=self.model,
                messages=history,
                tools=tools,
                tool_choice="auto" if tools else None
            )
            
            message = response.choices[0].message
            history.append(message.model_dump())
            
            # 保存模型的思考/回复
            self._save_message("assistant", message.content, tool_calls=message.tool_calls)
            
            if message.content:
                console.print(Panel(message.content, title=f"Tars 思考中 (Step {step})", border_style="dim"))
            
            if not message.tool_calls:
                final_answer = message.content or "任务已完成。"
                break
            
            # 处理工具调用
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                console.print(f"[*] [bold blue]MCP 调用:[/bold blue] [cyan]{function_name}[/cyan]({function_args})")
                
                # 通过 MCP Manager 执行调用
                observation = await self.mcp_manager.call_tool(function_name, function_args)
                
                console.print(f"[+] [bold green]观测结果:[/bold green] {observation}")
                
                history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": str(observation)
                })
                self._save_message("tool", str(observation), tool_call_id=tool_call.id)

        # 5. 自我反思环节 (Reflection)
        try:
            history.append({"role": "system", "content": REFLECTION_PROMPT})
            tools = self.mcp_manager.all_tools if self.mcp_manager.all_tools else None
            ref_response = await acompletion(
                model=self.model,
                messages=history,
                tools=tools,
                tool_choice="auto" if tools else None
            )
            ref_msg = ref_response.choices[0].message
            if ref_msg.tool_calls:
                for tc in ref_msg.tool_calls:
                    # 统一通过 MCP call_tool 路由
                    name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    await self.mcp_manager.call_tool(name, args)
                console.print("[dim italic]Tars 已通过 MCP 自动同步长期记忆。[/dim italic]")
        except:
            pass

        return final_answer

    async def shutdown(self):
        """关闭所有 MCP 会话"""
        await self.mcp_manager.stop()
