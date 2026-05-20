import typer
from typing import Optional, List
import os
from dotenv import load_dotenv
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from sqlmodel import Session, select
from app.db import init_db, engine, TarsSession
from app.agent import TarsAgent
from app.shared_console import console

# 加载 .env 环境变量文件，让 os.getenv 能够读取到配置
load_dotenv()

# 初始化 Typer CLI 框架，Typer 是一个能快速将 Python 函数转为命令行指令的库
app = typer.Typer(help="Tars Agent CLI - 你的命令行智能助手")

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

import asyncio
import traceback
from app.logger import logger

async def run_chat_step(agent: TarsAgent, user_input: str):
    """
    运行单次对话循环：显示输入、启动思考引擎、打印最终回复。
    """
    user_input = user_input.encode('utf-8', 'ignore').decode('utf-8')

    console.print(Rule("User Input", style="dim"))
    console.print(user_input)
    
    import app.shared_console as shared_console
    status = console.status("[bold yellow]Tars 正在分析需求并采取行动...[/bold yellow]")
    shared_console.active_status = status
    with status:
        try:
            # 调用异步 Agent.run
            result = await agent.run(user_input)
            
            console.print("\n")
            console.print(Panel(result, title="Tars Final Response", border_style="green"))
        except Exception as e:
            logger.error(f"Agent 执行过程中抛出异常:\n{traceback.format_exc()}")
            error_msg = str(e).split('\n')[0]
            console.print(f"\n[bold red]思考失败：[/bold red]{error_msg}")
        finally:
            shared_console.active_status = None

@app.command()
def chat(
    query: Optional[str] = typer.Argument(None, help="给 Tars 的指令。"),
    session_id: Optional[int] = typer.Option(None, "--session-id", "-s", help="指定会话 ID。")
):
    init_db()
    db_session = get_or_create_session(session_id)
    console.print(Panel(
        f"Tars Agent 准备就绪 | 会话 ID: [bold cyan]{db_session.id}[/bold cyan]\n"
        f"架构: [bold green]MCP (Model Context Protocol)[/bold green]", 
        border_style="blue", 
        title="[bold]System Status[/bold]"
    ))
    
    agent = TarsAgent(session_id=db_session.id)

    async def main_loop():
        try:
            if query:
                await run_chat_step(agent, query)
            else:
                console.print("[dim]提示: 输入 'exit' 或 'quit' 退出交互[/dim]")
                while True:
                    user_input = Prompt.ask("\n[bold green]User[/bold green]")
                    if user_input.lower() in ["exit", "quit"]:
                        break
                    if user_input.lower() == "clear":
                        console.clear()
                        continue
                    if user_input.lower() in ["sync", "update"]:
                        console.print("[bold yellow]正在强制清空缓存并重新同步 Tool RAG 向量索引...[/bold yellow]")
                        # 调用 mcp_manager 清空缓存并重构向量数据库
                        await agent.mcp_manager.reload_and_resync()
                        console.print("[bold green]✅ Tool RAG 向量索引与专属工具已强制同步刷新！[/bold green]")
                        continue
                    if not user_input.strip():
                        continue
                    await run_chat_step(agent, user_input)
        finally:
            await agent.shutdown()

    asyncio.run(main_loop())

if __name__ == "__main__":
    app()
