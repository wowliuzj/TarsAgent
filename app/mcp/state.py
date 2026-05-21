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
    precision_level: str = "L3"

class AuditEntry(BaseModel):
    node_name: str
    decision: str # approved, rejected
    reason: Optional[str] = None

class PlannerOutput(BaseModel):
    reasoning: str = Field(description="PM的规划与任务拆解思考过程")
    subtasks: List[SubTask] = Field(description="拆解出的具体子任务列表，带精度评级 (L1-L6)")

class ExecutorThought(BaseModel):
    reasoning: str = Field(description="执行者的思考与工具调用推导")
    confidence: float = Field(description="动作执行的自信度自评得分 (0.0 到 1.0)")

class AuditorVerdict(BaseModel):
    verdict: str = Field(description="审计判定结果，必须为 'approved' 或 'rejected'")
    reason: Optional[str] = Field(None, description="若是被驳回 (rejected)，必须写明具体具体的修正意见")

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
