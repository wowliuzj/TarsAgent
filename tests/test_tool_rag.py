import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session
from app.db import MCPToolIndex
from app.mcp.client_manager import MCPClientManager

@pytest.mark.asyncio
@patch("litellm.embedding")
async def test_get_tools_for_query_filtering(mock_embedding, db_session: Session):
    """验证 Tool RAG：核心基础设施工具 100% 自动合并，特种工具仅根据语义检索召回。"""
    # 1. 模拟 litellm.embedding 的返回，匹配 3072 高维空间
    mock_response = MagicMock()
    mock_response.data = [{'embedding': [0.1] * 3072}]
    mock_embedding.return_value = mock_response

    # 2. 插入核心工具
    core_tool = MCPToolIndex(
        server_name="system_runtime",
        tool_name="write_file",
        description="Writes content to a file",
        embedding=[0.0] * 3072,
        tool_schema={"name": "write_file", "description": "Writes content"}
    )
    
    # 3. 插入相关的特种工具
    matched_special_tool = MCPToolIndex(
        server_name="crypto_market",
        tool_name="get_crypto_price",
        description="Retrieves live crypto prices",
        embedding=[0.11] * 3072, # 与 mock_embedding (0.1) 极其接近，距离短
        tool_schema={"name": "get_crypto_price", "description": "Get crypto price"}
    )
    
    # 4. 插入不相关的特种工具
    unmatched_special_tool = MCPToolIndex(
        server_name="github_ops",
        tool_name="create_issue",
        description="Creates an issue in a GitHub repository",
        embedding=[0.9] * 3072, # 距离 mock_embedding 极远，不应被召回
        tool_schema={"name": "create_issue", "description": "Create issue"}
    )
    
    db_session.add(core_tool)
    db_session.add(matched_special_tool)
    db_session.add(unmatched_special_tool)
    db_session.commit()

    # 5. 实例化 MCP 客户端管理器并触发 Tool RAG 检索
    manager = MCPClientManager(servers_dir="mcp_servers")
    
    # top_k 设为 1，确保最多只召回一个最相近的特种工具
    retrieved_tools = await manager.get_tools_for_query("Query about BTC prices", top_k=1)
    
    # 6. 断言结果
    # - 核心工具 (write_file) 必须存在（默认 100% 注入）
    # - 与查询最接近的特种工具 (get_crypto_price) 应该被召回
    # - 不相关的特种工具 (create_issue) 应该被过滤掉
    retrieved_names = [t["function"]["name"] for t in retrieved_tools]
    assert "write_file" in retrieved_names
    assert "get_crypto_price" in retrieved_names
    assert "create_issue" not in retrieved_names
    
    # 校验模拟的 embedding 接口被调用了一次
    mock_embedding.assert_called_once()
