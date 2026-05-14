import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlmodel import SQLModel, Field, Session, create_engine, select, Relationship, Column, JSON
from pgvector.sqlalchemy import Vector

# 获取数据库连接 URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://tars:tars_pass@localhost:5432/tars_db")

engine = create_engine(DATABASE_URL)

class TarsSession(SQLModel, table=True):
    __tablename__ = "sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    session_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    messages: List["TarsMessage"] = Relationship(back_populates="session")

class TarsMessage(SQLModel, table=True):
    __tablename__ = "messages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id")
    role: str # user, assistant, system, tool
    content: Optional[str] = None
    
    # 用于存储 Tool Calls (OpenAI 格式)
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSON))
    # 对于 role="tool" 的消息，记录对应的 call_id
    tool_call_id: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    session: TarsSession = Relationship(back_populates="messages")

# 预留向量存储表 (将来用于 RAG)
class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledge_base"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    # 假设向量维度为 1536 (OpenAI standard) 或 768/3072 (Gemini/Gemma)
    embedding: Any = Field(sa_column=Column(Vector(1536))) 
    kb_metadata: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

from sqlalchemy import text

def init_db():
    # 1. 首先激活 PGVector 扩展
    with Session(engine) as session:
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        session.commit()

    # 2. 然后再创建所有表
    SQLModel.metadata.create_all(engine)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
