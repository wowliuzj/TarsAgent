import enum
from typing import List, Dict, Any, Optional, Annotated
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict
import operator

class Lane(str, enum.Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    AUDIT = "audit"

class Mission(BaseModel):
    id: str
    goal: str
    milestones: List[str] = []
    current_milestone_index: int = 0

class SubTask(BaseModel):
    id: str
    description: str
    status: str = "pending" # pending, in_progress, completed, failed
    result: Optional[str] = None

class AuditEntry(BaseModel):
    node_name: str
    decision: str # approved, rejected
    reason: Optional[str] = None

class TarsState(TypedDict):
    """Tars Harness Protocol (THP) 兼容的状态定义"""
    
    # 任务元数据
    mission: Mission
    
    # 历史记录 (使用 Annotated 和 operator.add 以支持 LangGraph 的消息追加)
    history: Annotated[List[BaseMessage], operator.add]
    
    # 共享记忆
    shared_memory: Dict[str, Any]
    
    # 任务池
    task_pool: List[SubTask]
    
    # 审计日志
    audit_log: List[AuditEntry]
    
    # 当前泳道
    current_lane: Lane
    
    # 下一节点 (用于逻辑路由)
    next_step: Optional[str]
    
    # Phase 2 控制流
    current_task_index: int
    executor_retries: int
    planner_retries: int
    audit_feedback: str
