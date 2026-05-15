import os
import json
from typing import List, Dict, Any
from litellm import completion
from app.db import engine, TarsMessage, TarsSession
from app.tools import TOOLS, TOOL_MAP
from sqlmodel import Session, select
from rich.console import Console
from rich.panel import Panel

# 初始化 Rich 控制台，用于在终端显示格式化内容
console = Console()

class TarsAgent:
    def __init__(self, session_id: int, model: str = None):
        """
        初始化 Tars Agent。
        
        Args:
            session_id: 数据库会话ID，用于追踪上下文。
            model: 指定使用的模型 ID，如果不指定则从环境变量读取。
        """
        self.session_id = session_id
        self.model = model or os.getenv("MODEL_NAME", "gemini/gemini-1.5-flash")
        self.system_prompt = self._load_soul()

    def _load_soul(self) -> str:
        """从根目录加载 SOUL.md 作为 System Prompt。"""
        try:
            with open("SOUL.md", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            # 如果文件丢失，提供一个最基础的兜底描述
            return "你是一个名为 Tars 的 AI 助手，性格理性、简洁、高效。"

    def _get_history(self) -> List[Dict[str, Any]]:
        """从数据库中检索当前会话的所有历史消息，构造为大模型所需的 messages 格式。"""
        with Session(engine) as session:
            # 按时间顺序查询所有消息
            statement = select(TarsMessage).where(TarsMessage.session_id == self.session_id).order_by(TarsMessage.created_at)
            results = session.exec(statement).all()
            
            # 始终以 System Prompt 开头
            history = [{"role": "system", "content": self.system_prompt}]
            for msg in results:
                m = {"role": msg.role, "content": msg.content}
                # 如果是工具调用相关的消息，需要包含 tool_calls 或 tool_call_id
                if msg.tool_calls:
                    m["tool_calls"] = msg.tool_calls
                if msg.tool_call_id:
                    m["tool_call_id"] = msg.tool_call_id
                history.append(m)
            return history

    def _save_message(self, role: str, content: str = None, tool_calls: List = None, tool_call_id: str = None):
        """将 Agent 或用户的消息持久化到数据库。"""
        # LiteLLM 返回的 tool_calls 是 Pydantic 对象，必须转为 dict 才能存入 Postgres 的 JSONB 字段
        serializable_tool_calls = None
        if tool_calls:
            serializable_tool_calls = []
            for tc in tool_calls:
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
        """
        执行 ReAct (Reasoning and Acting) 循环。
        这个函数会驱动 Agent 不断思考，直到解决问题或达到步数上限。
        """
        # 1. 首先记录用户的提问
        self._save_message("user", user_input)
        
        max_steps = 10  # 防止无限循环的保险机制
        step = 0
        
        while step < max_steps:
            step += 1
            # 2. 获取包含历史上下文的所有消息
            messages = self._get_history()
            
            # --- 新增：显示请求状态 ---
            console.print(f"\n[bold yellow]>>> Step {step}[/bold yellow] | [dim]正在调用模型: [bold cyan]{self.model}[/bold cyan] ...[/dim]")
            
            # 3. 调用大语言模型进行决策
            # 在这里模型会分析当前的所有信息（历史+观察结果）
            response = completion(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            response_msg = response.choices[0].message
            content = response_msg.content # 这里的 content 就是模型的“思考”或“最终回答”
            tool_calls = response_msg.get("tool_calls", None)
            
            # --- 显示模型的思考过程 ---
            if content:
                # 使用 Panel 将思考过程包裹起来，使其在终端中清晰可见
                console.print(Panel(content, title=f"Tars 思考中 (Step {step})", border_style="dim yellow"))
            
            # 4. 保存模型生成的回复到数据库
            self._save_message("assistant", content, tool_calls=tool_calls)
            
            # 如果模型没有请求调用任何工具，说明它认为任务已经完成，直接返回结果
            if not tool_calls:
                return content

            # 5. 如果模型请求调用工具，则依次执行它们
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                # 解析模型传来的参数 (JSON 字符串)
                function_args = json.loads(tool_call.function.arguments)
                
                # 在控制台提示用户正在进行的操作
                console.print(f"[*] [bold blue]执行工具:[/bold blue] [cyan]{function_name}[/cyan]({function_args})")
                
                # 从工具映射表中找到对应的 Python 函数
                tool_func = TOOL_MAP.get(function_name)
                if tool_func:
                    try:
                        # 执行真实的工具逻辑（如读写文件、执行命令）
                        observation = tool_func(**function_args)
                    except Exception as e:
                        observation = f"工具执行异常: {str(e)}"
                else:
                    observation = f"错误: 系统中未注册工具 {function_name}"
                
                # 6. 保存工具执行结果 (Observation)，role 设为 "tool"
                # 这是 ReAct 循环的关键：模型会在下一轮看到这个结果，并基于此进行下一步思考
                self._save_message("tool", observation, tool_call_id=tool_call.id)
                
                # 在控制台显示观察到的结果
                console.print(f"[+] [bold green]观察结果:[/bold green] {observation}")

        return "已达到最大步数限制，任务未能由 Tars 自动闭环。"
