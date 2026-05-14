import os
import json
from typing import List, Dict, Any
from litellm import completion
from app.db import engine, TarsMessage, TarsSession
from app.tools import TOOLS, TOOL_MAP
from sqlmodel import Session, select

class TarsAgent:
    def __init__(self, session_id: int, model: str = None):
        self.session_id = session_id
        self.model = model or os.getenv("MODEL_NAME", "gemini/gemini-1.5-flash")
        self.system_prompt = self._load_soul()

    def _load_soul(self) -> str:
        """加载 SOUL.md 作为系统提示词的核心。"""
        try:
            with open("SOUL.md", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return "你是一个名为 Tars 的 AI 助手。"

    def _get_history(self) -> List[Dict[str, Any]]:
        """从数据库加载当前会话的历史记录。"""
        with Session(engine) as session:
            statement = select(TarsMessage).where(TarsMessage.session_id == self.session_id).order_by(TarsMessage.created_at)
            results = session.exec(statement).all()
            
            history = [{"role": "system", "content": self.system_prompt}]
            for msg in results:
                m = {"role": msg.role, "content": msg.content}
                if msg.tool_calls:
                    m["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    m["tool_call_id"] = msg.tool_call_id
                history.append(m)
            return history

    def _save_message(self, role: str, content: str = None, tool_calls: List = None, tool_call_id: str = None):
        """保存单条消息到数据库。"""
        # 确保 tool_calls 是可序列化的 (转为 dict)
        serializable_tool_calls = None
        if tool_calls:
            serializable_tool_calls = []
            for tc in tool_calls:
                # 如果是对象，转为 dict；如果是 dict，直接用
                if hasattr(tc, "model_dump"):
                    serializable_tool_calls.append(tc.model_dump())
                elif hasattr(tc, "dict"):
                    serializable_tool_calls.append(tc.dict())
                else:
                    serializable_tool_calls.append(tc)

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

    def run(self, user_input: str):
        """执行 ReAct 循环。"""
        # 1. 保存用户输入
        self._save_message("user", user_input)
        
        max_steps = 10
        step = 0
        
        while step < max_steps:
            step += 1
            messages = self._get_history()
            
            # 2. 调用 LLM
            response = completion(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            response_msg = response.choices[0].message
            content = response_msg.content
            tool_calls = response_msg.get("tool_calls", None)
            
            # 3. 保存 LLM 的回复 (即使只有 tool_calls)
            self._save_message("assistant", content, tool_calls=tool_calls)
            
            if not tool_calls:
                # 如果没有工具调用，说明已经得到最终答案
                return content

            # 4. 执行工具调用
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                print(f"[*] 正在调用工具: {function_name}({function_args})")
                
                # 获取工具函数并执行
                tool_func = TOOL_MAP.get(function_name)
                if tool_func:
                    observation = tool_func(**function_args)
                else:
                    observation = f"错误: 未找到工具 {function_name}"
                
                # 5. 保存工具执行结果 (Observation)
                self._save_message("tool", observation, tool_call_id=tool_call.id)
                print(f"[+] 观察结果: {observation}")

        return "已达到最大步数限制，未能完成任务。"
