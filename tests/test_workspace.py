import pytest
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessage, ToolMessage
from app.mcp.graph import TarsGraphBuilder
from app.mcp.state import TarsState
from mcp_servers.system_runtime.src.server import run_terminal_command

def test_run_terminal_command_cwd_aligned():
    """验证 run_terminal_command 的 cwd 已对齐到项目根目录。"""
    # 执行 pwd / ls 命令，确认返回结果是项目根目录的内容
    res = run_terminal_command("pwd")
    assert "data/workspace" not in res  # 确保不再在 data/workspace 下执行
    
    res_files = run_terminal_command("ls")
    # 根目录下必然存在 requirements.txt, app 等文件夹/文件
    assert "requirements.txt" in res_files
    assert "app" in res_files
    assert "tests" in res_files

@pytest.mark.asyncio
async def test_workspace_interceptor_paths():
    """验证工作区在开放目录下的正常读写行为（无重定向）。"""
    # 1. Mock TarsGraphBuilder 中的 agent 实例和 mcp_manager
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    mock_mcp_manager.call_tool = AsyncMock(return_value="success")
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # 2. Case A: 写入 article.md -> 不应拦截重定向，直接物理自由写入
    state_a = {
        "history": [
            AIMessage(content="Confidence: 0.95", tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "article.md", "content": "test"},
                "id": "call_1"
            }])
        ]
    }
    await builder.tool_node(state_a)
    mock_mcp_manager.call_tool.assert_called_with(
        "write_file", 
        {"file_path": "article.md", "content": "test"}
    )
    
    # 3. Case B: 写入允许的临时目录 tmp/scrape.py -> 不应拦截重定向
    state_b = {
        "history": [
            AIMessage(content="Confidence: 0.95", tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "tmp/scrape.py", "content": "print(1)"},
                "id": "call_2"
            }])
        ]
    }
    await builder.tool_node(state_b)
    mock_mcp_manager.call_tool.assert_called_with(
        "write_file", 
        {"file_path": "tmp/scrape.py", "content": "print(1)"}
    )

@pytest.mark.asyncio
async def test_workspace_interceptor_list_files():
    """验证 list_files 的路径自由列表查询行为（无重定向）。"""
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    mock_mcp_manager.call_tool = AsyncMock(return_value="dir_list")
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # Case A: 查询允许的 data/ 目录 -> 不拦截
    state_a = {
        "history": [
            AIMessage(content="Confidence: 0.95", tool_calls=[{
                "name": "list_files",
                "args": {"directory": "data/article"},
                "id": "call_4"
            }])
        ]
    }
    await builder.tool_node(state_a)
    mock_mcp_manager.call_tool.assert_called_with(
        "list_files", 
        {"directory": "data/article"}
    )
    
    # Case B: 查询不合规的其它目录 -> 亦不拦截重定向，物理目录完全放开
    state_b = {
        "history": [
            AIMessage(content="Confidence: 0.95", tool_calls=[{
                "name": "list_files",
                "args": {"directory": "sensitive_folder"},
                "id": "call_5"
            }])
        ]
    }
    await builder.tool_node(state_b)
    mock_mcp_manager.call_tool.assert_called_with(
        "list_files", 
        {"directory": "sensitive_folder"}
    )

@pytest.mark.asyncio
async def test_confidence_and_safety_hitl(monkeypatch):
    """验证置信度低于阈值或触发高危动作时，HITL 人机协同介入的处理逻辑。"""
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    mock_mcp_manager.call_tool = AsyncMock(return_value="tool_done")
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # 1. 模拟用户手动拒绝授权 (approved = False)
    mock_prompt = MagicMock(return_value=False)
    monkeypatch.setattr("app.mcp.graph.prompt_user_intervention", mock_prompt)
    
    state_refused = {
        "history": [
            AIMessage(content="Confidence: 0.70", tool_calls=[{  # 置信度低于 0.85
                "name": "write_file",
                "args": {"file_path": "data/article.md", "content": "leak"},
                "id": "call_refuse"
            }])
        ]
    }
    
    res = await builder.tool_node(state_refused)
    tool_msg = res["history"][0]
    
    # 验证是否触发了人机协同介入
    mock_prompt.assert_called_once()
    # 验证工具物理调用未发生
    mock_mcp_manager.call_tool.assert_not_called()
    # 验证返回了安全阻断回执以促进 AI 自愈
    assert "安全阻断" in tool_msg.content
    assert "人类控制者手动拒绝了此授权" in tool_msg.content

    # 2. 模拟用户手动授权通过 (approved = True)
    mock_prompt.reset_mock()
    mock_prompt.return_value = True
    
    state_approved = {
        "history": [
            AIMessage(content="Confidence: 0.70", tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "data/article.md", "content": "leak"},
                "id": "call_approve"
            }])
        ]
    }
    
    res_app = await builder.tool_node(state_approved)
    tool_msg_app = res_app["history"][0]
    
    # 验证用户被提问，且物理工具正常执行
    mock_prompt.assert_called_once()
    mock_mcp_manager.call_tool.assert_called_once_with(
        "write_file",
        {"file_path": "data/article.md", "content": "leak"}
    )
    assert tool_msg_app.content == "tool_done"

@pytest.mark.asyncio
async def test_workspace_interceptor_truncation():
    """验证大输出哨兵（Tool Output Truncation Safeguard）截断超出 50,000 字符的工具返回结果。"""
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    # 构造一个 60,000 字符的超长字符串
    massive_output = "A" * 60000
    mock_mcp_manager.call_tool = AsyncMock(return_value=massive_output)
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    state = {
        "history": [
            AIMessage(content="", tool_calls=[{
                "name": "read_file",
                "args": {"file_path": "data/article/large.md"},
                "id": "call_6"
            }])
        ]
    }
    
    res = await builder.tool_node(state)
    tool_msg = res["history"][0]
    
    # 1. 验证被截断结果已成功封装进 ToolMessage
    assert isinstance(tool_msg, ToolMessage)
    
    # 2. 验证内容确实被截取，并且带有哨兵提示
    content = tool_msg.content
    assert "系统安全卫兵提醒" in content
    assert "已自动为您安全截断前 50000 字符" in content
    assert "剩余 10000 字符已被系统安全自动截断" in content
    # 验证实际前缀加上被截断的前 50000 字符的长度正确性
    assert len(content) > 50000
    assert "A" * 50000 in content

@pytest.mark.asyncio
async def test_workspace_reflect_natural_response():
    """验证 reflect_node 能正确旁路纯闲聊文本以自然方式返回，并对复杂工具任务进行成果导向合成。"""
    from app.mcp.state import SubTask, Mission
    
    mock_agent = MagicMock()
    mock_agent._call_model = AsyncMock(return_value=AIMessage(content="mocked_synthesis"))
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # ------------------ Case A: 纯文本闲聊对话 ------------------
    state_a: TarsState = {
        "mission": Mission(id="m_1", goal="嗯，你心情如何？"),
        "task_pool": [SubTask(id="task_1", description="闲聊回复", status="completed")],
        "shared_memory": {
            "step_1_result": "作为 AI，我不具备情绪，但我很好，随时准备帮助你。"
        },
        "history": []
    }
    
    res_a = await builder.reflect_node(state_a)
    aimsg_a = res_a["history"][0]
    
    # 1. 验证它被 [直接对话通道] 拦截并直接返回，没有调用大模型合成 (旁路机制)
    mock_agent._call_model.assert_not_called()
    
    # 2. 验证返回内容以强制前缀开头并包含 Executor 原生回复
    assert aimsg_a.content.startswith("【Tars 收到您的指令，执行中...】")
    assert "作为 AI，我不具备情绪" in aimsg_a.content
    
    # ------------------ Case B: 包含工具返回的复杂任务 ------------------
    mock_agent._call_model.reset_mock()
    
    state_b: TarsState = {
        "mission": Mission(id="m_2", goal="抓取网页"),
        "task_pool": [
            SubTask(id="task_1", description="写入脚本", status="completed"),
            SubTask(id="task_2", description="运行抓取", status="completed")
        ],
        "shared_memory": {
            "step_1_result": '{"script_written": "tmp/scrape.py"}',
            "step_2_result": '{"status": "success", "content": "# Markdown content"}'
        },
        "history": []
    }
    
    res_b = await builder.reflect_node(state_b)
    aimsg_b = res_b["history"][0]
    
    # 1. 验证其触发了大模型合成整理
    mock_agent._call_model.assert_called_once()
    
    # 2. 验证合成提示词中包含了最新的成果呈现和防审计化要求
    called_messages = mock_agent._call_model.call_args[0][0]
    synthesis_prompt_content = called_messages[1].content
    assert "成果导向呈现" in synthesis_prompt_content
    assert "绝对禁止以“最终审计报告”" in synthesis_prompt_content
    assert aimsg_b.content == "mocked_synthesis"


@pytest.mark.asyncio
async def test_workspace_planner_node_for_conversational_chat():
    """验证 planner_node 能够正确且自适应地将主观或情感倾诉类的 Query（例如生硬度评价）制定为 1 步 L1 精度的计划。"""
    from app.mcp.state import Mission
    
    mock_agent = MagicMock()
    # 模拟 Planner 应该输出的符合 Rule 10 的单步计划文本
    mock_planner_output = "1. 友好温和地向用户解释为什么之前的回答有些生硬，表达歉意与理解，并承诺以后会用更生动自然的方式与之对话沟通。 (L1)"
    mock_agent._call_model = AsyncMock(return_value=AIMessage(content=mock_planner_output))
    mock_agent.mcp_manager = MagicMock()
    mock_agent.mcp_manager.get_tools_for_query = AsyncMock(return_value=[])
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    state = {
        "mission": Mission(id="m_3", goal="为什么你的回答总是那么生硬？"),
        "task_pool": [],
        "history": [],
        "planner_retries": 0
    }
    
    res = await builder.planner_node(state)
    task_pool = res["task_pool"]
    
    # 1. 验证仅生成了 1 个子任务
    assert len(task_pool) == 1
    # 2. 验证该子任务的精确度被精确地标记/解析为 L1
    assert task_pool[0].precision_level == "L1"
    # 3. 验证任务描述与原生预期一致
    assert "友好温和地向用户解释" in task_pool[0].description


