import os
import json
from typing import List, Dict, Any
from litellm import completion
from app.db import engine, TarsMessage, TarsSession
from app.tools import TOOLS, TOOL_MAP, memory_search, memory_save
from app.prompts import BASE_SYSTEM_PROMPT, MEMORY_CONTEXT_PROMPT, REFLECTION_PROMPT
from sqlmodel import Session, select
from rich.console import Console
from rich.panel import Panel

console = Console()

class TarsAgent:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.model = os.getenv("MODEL_NAME", "gemini/gemini-1.5-flash")

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

    def run(self, user_input: str) -> str:
        """运行 ReAct 循环，包含 RAG 检索和自我反思"""
        
        # 1. 保存用户输入
        self._save_message("user", user_input)
        
        # 2. 静默记忆检索 (RAG)
        # 即使这里失败，也不影响主流程
        try:
            memory_data = memory_search(user_input, top_k=2)
        except:
            memory_data = ""

        history = self._get_history()
        
        # 如果找回了相关记忆，将其注入到当前上下文
        if "找回的相关记忆" in memory_data:
            memory_prompt = MEMORY_CONTEXT_PROMPT.format(memory_content=memory_data)
            history.insert(1, {"role": "system", "content": memory_prompt})

        # 3. 主 ReAct 循环
        max_steps = 10
        step = 0
        final_answer = "未能在限步内完成任务。"
        
        while step < max_steps:
            step += 1
            console.print(f"\n[bold cyan]>>> Step {step}[/bold cyan] | 正在调用模型: {self.model} ...")
            
            response = completion(
                model=self.model,
                messages=history,
                tools=TOOLS,
                tool_choice="auto"
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
                
                console.print(f"[*] [bold blue]执行工具:[/bold blue] [cyan]{function_name}[/cyan]({function_args})")
                
                tool_func = TOOL_MAP.get(function_name)
                if tool_func:
                    observation = tool_func(**function_args)
                    console.print(f"[+] [bold green]观察结果:[/bold green] {observation}")
                    
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": str(observation)
                    })
                    self._save_message("tool", str(observation), tool_call_id=tool_call.id)
                else:
                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": f"Error: Tool {function_name} not found."
                    })

        # 4. 自我反思环节 (Reflection)
        try:
            history.append({"role": "system", "content": REFLECTION_PROMPT})
            ref_response = completion(
                model=self.model,
                messages=history,
                tools=TOOLS,
                tool_choice="auto"
            )
            ref_msg = ref_response.choices[0].message
            if ref_msg.tool_calls:
                for tc in ref_msg.tool_calls:
                    if tc.function.name == "memory_save":
                        args = json.loads(tc.function.arguments)
                        memory_save(**args)
                        console.print("[dim italic]Tars 已自动将重要信息存入长期记忆库。[/dim italic]")
        except Exception as e:
            # 反思环节失败不影响主任务结果，静默跳过
            pass

        return final_answer
