from sqlmodel import Session, select
from app.db import TarsSession, TarsMessage, MCPToolIndex, KnowledgeBase

def test_db_session_and_message_relationship(db_session: Session):
    """验证 TarsSession 与 TarsMessage 表的创建、数据存取及一对多关联关系。"""
    # 1. 创建并保存一个会话
    session = TarsSession(session_metadata={"platform": "pytest_test"})
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    
    assert session.id is not None
    assert session.session_metadata["platform"] == "pytest_test"
    
    # 2. 创建并关联保存消息
    msg1 = TarsMessage(session_id=session.id, role="user", content="Hi Tars!")
    msg2 = TarsMessage(session_id=session.id, role="assistant", content="Hello Human!")
    db_session.add(msg1)
    db_session.add(msg2)
    db_session.commit()
    
    # 3. 验证一对多关联关系 (按 id 排序确保断言不因默认查询顺序抖动)
    db_session.refresh(session)
    assert len(session.messages) == 2
    messages_sorted = sorted(session.messages, key=lambda m: m.id or 0)
    assert messages_sorted[0].role == "user"
    assert messages_sorted[0].content == "Hi Tars!"
    assert messages_sorted[1].role == "assistant"
    assert messages_sorted[1].content == "Hello Human!"

def test_mcp_tool_index_mapping(db_session: Session):
    """验证 MCPToolIndex 表结构映射，包括 JSONSchema 和 PGVector 高维数值的写入与查询。"""
    mock_embedding = [0.1] * 3072 # 匹配我们在环境里设定的 3072 高维空间
    
    tool = MCPToolIndex(
        server_name="mock_server",
        tool_name="mock_calculator",
        description="A specialized math tool to calculate numbers",
        embedding=mock_embedding,
        tool_schema={
            "name": "mock_calculator",
            "description": "A specialized math tool to calculate numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"}
                }
            }
        }
    )
    db_session.add(tool)
    db_session.commit()
    db_session.refresh(tool)
    
    # 验证主键与参数正确存储
    assert tool.id is not None
    assert tool.server_name == "mock_server"
    assert tool.tool_name == "mock_calculator"
    assert tool.tool_schema["parameters"]["type"] == "object"
    
    # 从数据库再次读出校验
    stmt = select(MCPToolIndex).where(MCPToolIndex.tool_name == "mock_calculator")
    queried_tool = db_session.exec(stmt).first()
    assert queried_tool is not None
    assert len(queried_tool.embedding) == 3072
