import typer
from typing import Optional, List
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from sqlmodel import Session, select
from app.db import init_db, engine, TarsSession
from app.agent import TarsAgent

# 加载 .env 环境变量文件，让 os.getenv 能够读取到配置
load_dotenv()

# 初始化 Typer CLI 框架，Typer 是一个能快速将 Python 函数转为命令行指令的库
app = typer.Typer(help="Tars Agent CLI - 你的命令行智能助手")
console = Console()

def get_or_create_session(session_id: int = None) -> TarsSession:
    """
    根据 ID 获取现有会话，或者创建一个全新的会话。
    会话机制确保了 Tars 能够通过数据库关联并找回之前的对话历史。
    """
    with Session(engine) as session:
        if session_id:
            # 尝试通过 ID 从 TarsSession 表中查找
            db_session = session.get(TarsSession, session_id)
            if db_session:
                return db_session
        
        # 如果未找到或未提供 ID，则生成一个新的会话记录
        new_session = TarsSession()
        session.add(new_session)
        session.commit()
        session.refresh(new_session)
        return new_session

@app.command()
def chat(
    query: Optional[str] = typer.Argument(None, help="给 Tars 的指令。如果不填，系统将进入‘持续对话’模式。"),
    session_id: Optional[int] = typer.Option(None, "--session-id", "-s", help="指定特定的会话 ID 来恢复之前的上下文。")
):
    """
    与 Tars Agent 进行对话的主要入口命令。
    """
    
    # 1. 初始化数据库结构：确保表已创建，PGVector 扩展已激活
    init_db()
    
    # 2. 初始化会话上下文
    db_session = get_or_create_session(session_id)
    console.print(Panel(
        f"Tars Agent 准备就绪 | 会话 ID: [bold cyan]{db_session.id}[/bold cyan]\n"
        f"模式: {'[yellow]单次指令[/yellow]' if query else '[green]持续对话[/green]'}", 
        border_style="blue", 
        title="[bold]System Status[/bold]"
    ))
    
    # 3. 实例化核心 Agent
    agent = TarsAgent(session_id=db_session.id)

    if query:
        # --- 模式 A：单次指令 ---
        # 适用于执行一次性的任务，如 `./tars "创建一个 README"`
        run_chat_step(agent, query)
    else:
        # --- 模式 B：交互式对话 ---
        # 适用于像使用 ChatGPT 一样反复交流
        console.print("[dim]提示: 输入 'exit' 或 'quit' 退出交互，输入 'clear' 清空屏幕[/dim]")
        while True:
            # 使用 Rich 的 Prompt 提示符接收用户输入
            user_input = Prompt.ask("\n[bold green]User[/bold green]")
            
            if user_input.lower() in ["exit", "quit"]:
                console.print("[yellow]Tars 状态：已离线。[/yellow]")
                break
            if user_input.lower() == "clear":
                console.clear()
                continue
            if not user_input.strip():
                continue
                
            # 执行本轮对话
            run_chat_step(agent, user_input)

import traceback
from app.logger import logger

def run_chat_step(agent: TarsAgent, user_input: str):
    """
    运行单次对话循环：显示输入、启动思考引擎、打印最终回复。
    """
    # 强行清洗输入内容，防止回退符或不可见字符导致的 UTF-8 编码错误
    user_input = user_input.encode('utf-8', 'ignore').decode('utf-8')

    console.print(Rule("User Input", style="dim"))
    console.print(user_input)
    
    # 在 Agent 思考期间展示一个动态加载动画 (Spinner)
    with console.status("[bold yellow]Tars 正在分析需求并采取行动...[/bold yellow]"):
        try:
            # 调用 Agent.run 启动 ReAct 逻辑循环
            result = agent.run(user_input)
            
            # 打印模型最终确认生成的回复
            console.print("\n")
            console.print(Panel(result, title="Tars Final Response", border_style="green"))
        except Exception as e:
            # 记录详细错误到日志，不在屏幕显示
            logger.error(f"Agent 执行过程中抛出异常:\n{traceback.format_exc()}")
            
            # 提取异常的第一行作为提示
            error_msg = str(e).split('\n')[0]
            console.print(f"\n[bold red]思考失败：[/bold red]{error_msg}")
            console.print("[dim]详情请查阅 logs/tars.log[/dim]")

if __name__ == "__main__":
    # 启动 Typer 应用
    app()
