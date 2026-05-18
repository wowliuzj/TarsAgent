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
    """验证工作区拦截器在 data/ 与 tmp/ 冷热分离新规则下的路径修改行为。"""
    # 1. Mock TarsGraphBuilder 中的 agent 实例和 mcp_manager
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    mock_mcp_manager.call_tool = AsyncMock(return_value="success")
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # 2. Case A: 写入允许的数据目录 data/article/article.md -> 不应拦截重定向
    state_a = {
        "history": [
            AIMessage(content="", tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "data/article/article.md", "content": "test"},
                "id": "call_1"
            }])
        ]
    }
    await builder.tool_node(state_a)
    mock_mcp_manager.call_tool.assert_called_with(
        "write_file", 
        {"file_path": "data/article/article.md", "content": "test"}
    )
    
    # 3. Case B: 写入允许的临时目录 tmp/scrape.py -> 不应拦截重定向
    state_b = {
        "history": [
            AIMessage(content="", tool_calls=[{
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
    
    # 4. Case C: 写入非法/未分类的根级文件 article.md -> 应该拦截并安全重定向至 tmp/article.md
    state_c = {
        "history": [
            AIMessage(content="", tool_calls=[{
                "name": "write_file",
                "args": {"file_path": "article.md", "content": "leak"},
                "id": "call_3"
            }])
        ]
    }
    await builder.tool_node(state_c)
    mock_mcp_manager.call_tool.assert_called_with(
        "write_file", 
        {"file_path": "tmp/article.md", "content": "leak"}
    )

@pytest.mark.asyncio
async def test_workspace_interceptor_list_files():
    """验证 list_files 的路径过滤拦截行为。"""
    mock_agent = MagicMock()
    mock_mcp_manager = MagicMock()
    mock_mcp_manager.call_tool = AsyncMock(return_value="dir_list")
    mock_agent.mcp_manager = mock_mcp_manager
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # Case A: 查询允许的 data/ 目录 -> 不拦截
    state_a = {
        "history": [
            AIMessage(content="", tool_calls=[{
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
    
    # Case B: 查询不合规的根级或其它目录 -> 自动重定向至 tmp 目录
    state_b = {
        "history": [
            AIMessage(content="", tool_calls=[{
                "name": "list_files",
                "args": {"directory": "sensitive_folder"},
                "id": "call_5"
            }])
        ]
    }
    await builder.tool_node(state_b)
    mock_mcp_manager.call_tool.assert_called_with(
        "list_files", 
        {"directory": "tmp"}
    )

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

