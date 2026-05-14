import typer
from typing import Optional, List
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from rich.panel import Panel
from sqlmodel import Session, select
from app.db import init_db, engine, TarsSession
from app.agent import TarsAgent

# 加载环境变量
load_dotenv()

app = typer.Typer()
console = Console()

def get_or_create_session(session_id: int = None) -> TarsSession:
    """获取现有会话或创建新会话。"""
    with Session(engine) as session:
        if session_id:
            db_session = session.get(TarsSession, session_id)
            if db_session:
                return db_session
        
        # 创建新会话
        new_session = TarsSession()
        session.add(new_session)
        session.commit()
        session.refresh(new_session)
        return new_session

@app.command()
def chat(
    query: Optional[str] = typer.Argument(None, help="你的指令 (如果不输入则进入交互模式)"),
    session_id: Optional[int] = typer.Option(None, "--session-id", "-s", help="会话ID")
):
    """与 Tars Agent 进行对话。"""
    
    # 1. 初始化数据库
    init_db()
    
    # 2. 获取或创建会话
    db_session = get_or_create_session(session_id)
    console.print(Panel(f"Tars Agent | Session ID: [bold cyan]{db_session.id}[/bold cyan]", border_style="blue"))
    
    agent = TarsAgent(session_id=db_session.id)

    if query:
        # 单次指令模式
        run_chat_step(agent, query)
    else:
        # 交互模式
        console.print("[dim]提示: 输入 'exit' 或 'quit' 退出，输入 'clear' 清屏[/dim]")
        while True:
            user_input = Prompt.ask("\n[bold green]User[/bold green]")
            
            if user_input.lower() in ["exit", "quit"]:
                console.print("[yellow]Tars 离线。再见。[/yellow]")
                break
            if user_input.lower() == "clear":
                console.clear()
                continue
            if not user_input.strip():
                continue
                
            run_chat_step(agent, user_input)

def run_chat_step(agent: TarsAgent, user_input: str):
    """执行一步对话。"""
    console.print(Rule("User Input", style="dim"))
    console.print(user_input)
    
    with console.status("[bold yellow]Tars 正在思考与行动...[/bold yellow]"):
        try:
            result = agent.run(user_input)
            # 输出最终结果
            console.print("\n")
            console.print(Panel(result, title="Tars Response", border_style="green"))
        except Exception as e:
            console.print(f"\n[bold red]发生错误:[/bold red] {str(e)}")
            import traceback
            console.print(traceback.format_exc(), style="dim")

if __name__ == "__main__":
    app()
