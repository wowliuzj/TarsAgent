import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import os
import json
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage
from app.mcp.state import SubTask, Mission, PlannerOutput, ExecutorThought, AuditorVerdict, TarsState
from app.mcp.graph import (
    parse_confidence, 
    verify_state_invariants, 
    prune_history_messages, 
    TarsGraphBuilder
)

def test_planner_structured_output():
    """验证 parse_confidence 可以兼容地解析 THP 2.0 格式与降级正则"""
    # 1. 验证 JSON 格式的解析 (THP 2.0)
    json_thought = '{"reasoning": "Test run command", "confidence": 0.99}'
    assert parse_confidence(json_thought) == 0.99
    
    # 2. 验证 Markdown 包裹的 JSON
    markdown_thought = '```json\n{"reasoning": "Test run command", "confidence": 0.98}\n```'
    assert parse_confidence(markdown_thought) == 0.98
    
    # 3. 验证降级正则解析 (THP 1.0)
    legacy_thought = "Thinking... Confidence: 0.92"
    assert parse_confidence(legacy_thought) == 0.92
    
    # 4. 验证默认兜底
    assert parse_confidence("random string without anything") == 0.85

def test_state_assertions_invariants():
    """验证状态不变式 (Invariants) 校验"""
    # 构造合法的初始状态
    valid_state: TarsState = {
        "mission": Mission(id="test_mission", goal="Analyze repo"),
        "history": [HumanMessage(content="Analyze repo")],
        "shared_memory": {},
        "task_pool": [],
        "current_task_index": 0,
        "executor_retries": 0,
        "planner_retries": 0,
        "audit_feedback": ""
    }
    
    # 1. pre-check think 失败（任务池为空）
    with pytest.raises(AssertionError, match="Executor 'think' node requires a non-empty 'task_pool'"):
        verify_state_invariants("think", valid_state, is_post=False)
        
    # 2. 填充任务池但包含非法精度评级
    invalid_state = valid_state.copy()
    invalid_state["task_pool"] = [
        SubTask(id="task_1", description="Build", precision_level="L9") # 非法评级
    ]
    with pytest.raises(AssertionError, match="Invalid SubTask precision level 'L9'"):
        verify_state_invariants("planner", invalid_state, is_post=True)
        
    # 3. 正常校验通过
    correct_state = valid_state.copy()
    correct_state["task_pool"] = [
        SubTask(id="task_1", description="Build", precision_level="L6")
    ]
    verify_state_invariants("planner", correct_state, is_post=True) # 不抛异常

def test_history_pruning_sliding():
    """验证智能历史修剪器 (HistoryPruner) 的上下文窗口滑动限制"""
    # 构造总长度较小的 history
    short_history = [
        SystemMessage(content="Sys"),
        HumanMessage(content="Goal"),
        ToolMessage(content="short output", tool_call_id="1")
    ]
    pruned_short = prune_history_messages(short_history, max_chars=1000)
    assert len(pruned_short) == 3
    assert pruned_short[2].content == "short output"
    
    # 构造巨大字符长度的 history 触发修剪
    long_history = [
        SystemMessage(content="System instruction"),
        HumanMessage(content="User ultimate objective"),
    ]
    # 添加很多个巨大的 Tool 消息
    for i in range(15):
        long_history.append(AIMessage(content="", tool_calls=[{"id": f"c_{i}", "name": "run", "args": {}}]))
        long_history.append(ToolMessage(content="A" * 10000, tool_call_id=f"c_{i}"))
        
    # 执行修剪，最大字数限制设为 10000
    pruned_long = prune_history_messages(long_history, max_chars=10000)
    
    # 验证前 2 个核心引导消息没有被丢弃
    assert pruned_long[0].content == "System instruction"
    assert pruned_long[1].content == "User ultimate objective"
    
    # 验证较老的巨大 Tool 消息内容被进行了压缩截断，含有 "[修剪器截断" 关键字
    found_truncated = False
    for msg in pruned_long:
        if isinstance(msg, ToolMessage) and "[修剪器截断" in msg.content:
            found_truncated = True
            break
    assert found_truncated

@pytest.mark.asyncio
async def test_planner_node_structured_parsing():
    """验证 planner_node 能够正确请求 structured response 并解析"""
    mock_agent = MagicMock()
    mock_agent.mcp_manager = MagicMock()
    mock_agent.mcp_manager.get_tools_for_query = AsyncMock(return_value=[])
    
    # 模拟 Planner 返回合法的 PlannerOutput JSON
    planner_json = {
        "reasoning": "To achieve the goal, I split it into 2 parts.",
        "subtasks": [
            {"id": "task_1", "description": "Verify code", "precision_level": "L6"},
            {"id": "task_2", "description": "Write report", "precision_level": "L3"}
        ]
    }
    mock_response = AIMessage(content=json.dumps(planner_json))
    mock_agent._call_model = AsyncMock(return_value=mock_response)
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    state: TarsState = {
        "mission": Mission(id="m_1", goal="Verify structure"),
        "history": [HumanMessage(content="Verify structure")],
        "shared_memory": {},
        "task_pool": [],
        "current_task_index": 0,
        "executor_retries": 0,
        "planner_retries": 0,
        "audit_feedback": ""
    }
    
    res = await builder.planner_node(state)
    
    # 验证确实调用了 _call_model 且携带了 response_format=PlannerOutput
    mock_agent._call_model.assert_called_once()
    assert mock_agent._call_model.call_args[1]["response_format"] == PlannerOutput
    
    # 验证返回的任务池包含 2 个任务，且被正确填充
    assert len(res["task_pool"]) == 2
    assert res["task_pool"][0].description == "Verify code"
    assert res["task_pool"][0].precision_level == "L6"

@pytest.mark.asyncio
async def test_auditor_node_structured_parsing():
    """验证 auditor_node 能够正确请求 structured response 并裁决"""
    mock_agent = MagicMock()
    mock_agent.mcp_manager = MagicMock()
    
    # 模拟 Auditor 返回驳回
    auditor_json = {
        "verdict": "rejected",
        "reason": "Missing precision log traces."
    }
    mock_response = AIMessage(content=json.dumps(auditor_json))
    mock_agent._call_model = AsyncMock(return_value=mock_response)
    
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    state: TarsState = {
        "mission": Mission(id="m_1", goal="Verify structure"),
        "history": [HumanMessage(content="Verify structure")],
        "shared_memory": {"step_1_result": "Success"},
        "task_pool": [SubTask(id="task_1", description="Check", precision_level="L3")],
        "current_task_index": 1,
        "executor_retries": 0,
        "planner_retries": 0,
        "audit_feedback": ""
    }
    
    res = await builder.auditor_node(state)
    
    # 验证携带了 response_format=AuditorVerdict
    mock_agent._call_model.assert_called_once()
    assert mock_agent._call_model.call_args[1]["response_format"] == AuditorVerdict
    
    # 验证审计判定为驳回，且将 current_task_index 重置为 0，且 executor_retries 递增
    assert res["audit_feedback"] == "Missing precision log traces."
    assert res["executor_retries"] == 1
    assert res["current_task_index"] == 0

@pytest.mark.asyncio
async def test_l6_self_testing_healing_loop():
    """验证 L6 精度下自检失败触发自愈重试的完整闭环流程"""
    mock_agent = MagicMock()
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    state: TarsState = {
        "mission": Mission(id="m_1", goal="L6 Check"),
        "history": [HumanMessage(content="L6 Check"), AIMessage(content="Code written")],
        "shared_memory": {},
        "task_pool": [SubTask(id="task_1", description="L6 Code change", precision_level="L6")],
        "current_task_index": 0,
        "executor_retries": 0,
        "planner_retries": 0,
        "audit_feedback": ""
    }
    
    # 模拟 subprocess.run 返回 pytest 执行失败 (returncode = 1)
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stdout = "FAIL: test_assert_error"
    mock_process.stderr = ""
    
    with patch("subprocess.run", return_value=mock_process) as mock_run:
        res = await builder.register_step_node(state)
        
        # 确认 pytest 被运行
        mock_run.assert_called_once()
        
        # 验证没有推进索引且 executor_retries 被累加，并返回了自愈提示
        assert res["current_task_index"] == 0
        assert res["executor_retries"] == 1
        assert "L6 Sandbox 自愈哨兵警告" in res["history"][0].content
        assert "FAIL: test_assert_error" in res["history"][0].content

@pytest.mark.asyncio
async def test_response_unwrapping_double_defense():
    """验证简单聊天或合成节点中，成果脱壳提炼与双重防御机制的有效性"""
    # 1. 验证 reflect_node 能正确脱壳 JSON 并激活闲聊直接通道 (is_simple_chat = True)
    mock_agent = MagicMock()
    builder = TarsGraphBuilder(agent_instance=mock_agent)
    
    # 模拟 step_1_result 是一个带 reasoning 的 JSON string (Executor 强制结构化输出的结果)
    json_result = json.dumps({
        "reasoning": "【Tars 收到您的指令，执行中...】今天天气真好，祝您开心！",
        "confidence": 0.98
    })
    
    state: TarsState = {
        "mission": Mission(id="m_1", goal="今天天气怎么样？"),
        "history": [HumanMessage(content="今天天气怎么样？")],
        "shared_memory": {"step_1_result": json_result},
        "task_pool": [SubTask(id="task_1", description="闲聊问答", precision_level="L1")],
        "current_task_index": 1,
        "executor_retries": 0,
        "planner_retries": 0,
        "audit_feedback": ""
    }
    
    res = await builder.reflect_node(state)
    final_msg = res["history"][0]
    
    # 验证确实绕过了 LLM 成果整合合成，直接剥离了 JSON 壳，返回了纯净文本
    assert "今天天气真好，祝您开心！" in final_msg.content
    assert "{" not in final_msg.content
    assert "reasoning" not in final_msg.content

    # 2. 验证 app/agent.py 中的 TarsAgent.run 能正确脱壳合成终点的 JSON 兜底
    from app.agent import TarsAgent
    agent = TarsAgent(session_id=123)
    
    # 模拟 final_state 的 history 尾部是一个强行输出的 JSON AIMessage
    from langchain_core.messages import AIMessage
    mock_final_state = {
        "history": [
            HumanMessage(content="你好"),
            AIMessage(content=json.dumps({
                "reasoning": "【Tars 收到您的指令，执行中...】您好！很高兴为您服务。",
                "confidence": 0.95
            }))
        ]
    }
    
    # Mock graph.ainvoke 返回模拟状态
    agent.graph = MagicMock()
    agent.graph.ainvoke = AsyncMock(return_value=mock_final_state)
    
    final_response = await agent.run("你好")
    # 验证输出已被剥离 JSON，还原为纯净的 reasoning 内容
    assert final_response == "【Tars 收到您的指令，执行中...】您好！很高兴为您服务。"

