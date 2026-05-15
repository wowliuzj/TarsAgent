import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlmodel import SQLModel, Field, Session, create_engine, select, Relationship, Column, JSON
from pgvector.sqlalchemy import Vector
from sqlalchemy import text

# 获取数据库连接 URL。
# 默认指向 localhost (用于本地调试)，在 Docker 环境下会被 .env 中的 db:5432 覆盖。
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tars:tars_pass@localhost:5432/tars_db")

# 创建数据库引擎
engine = create_engine(DATABASE_URL)

class TarsSession(SQLModel, table=True):
    """
    会话模型：代表一段完整的对话任务。
    __tablename__ = "sessions" 指明在数据库中创建的表名。
    """
    __tablename__ = "sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # 使用 JSON 类型存储额外的元数据
    session_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    # 建立与 TarsMessage 的一对多关系，方便通过 session.messages 直接访问对话流
    messages: List["TarsMessage"] = Relationship(back_populates="session")

class TarsMessage(SQLModel, table=True):
    """
    消息模型：存储 ReAct 循环中的每一轮交互。
    """
    __tablename__ = "messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id")
    # 角色定义：user (用户), assistant (AI思考/回复), system (全局指令), tool (工具观察结果)
    role: str 
    content: Optional[str] = None
    
    # 核心字段：存储大模型返回的工具调用指令 (JSON 列表格式)
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    # 对于 role="tool" 的反馈消息，记录它是响应哪一个 call_id 的结果
    tool_call_id: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # 反向关联到会话
    session: TarsSession = Relationship(back_populates="messages")

class KnowledgeBase(SQLModel, table=True):
    """
    预留知识库模型：用于将来实现 RAG (检索增强生成)。
    使用 PGVector 扩展提供的 Vector 类型来存储 Embedding 向量。
    """
    __tablename__ = "knowledge_base"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    # 向量字段：用于语义搜索。1536 维度通常对应 OpenAI 的 embedding-3 系列，
    # 如果使用 Gemini/Gemma，可能需要调整为 768 或 3072。
    embedding: Any = Field(sa_column=Column(Vector(1536))) 
    # 元数据字段，改名为 kb_metadata 以避开 SQLModel 内置属性
    kb_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

def init_db():
    """
    初始化数据库的关键逻辑。
    """
    # 1. 必须要先手动执行 SQL 激活 PGVector 扩展，否则后续创建含 Vector 字段的表会报错。
    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        session.commit()

    # 2. 调用 SQLModel 的元数据方法，根据定义的 Class 自动创建所有表
    SQLModel.metadata.create_all(engine)

# 如果直接运行此脚本，则执行初始化并打印成功信息
if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
