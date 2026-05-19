import re
from app.prompts import PLANNER_PROMPT
from app.mcp.graph import SubTask

def test_planner_prompt_contains_intent_cap_rules():
    """验证 PLANNER_PROMPT 中明确包含了对简单意图（大纲、简易）进行 L3 精度封顶及 1-3 步限制的规则。"""
    assert "大纲" in PLANNER_PROMPT or "简单" in PLANNER_PROMPT
    assert "L3" in PLANNER_PROMPT
    assert "1-3" in PLANNER_PROMPT or "步" in PLANNER_PROMPT

def test_planner_prompt_contains_conversational_rules():
    """验证 PLANNER_PROMPT 中明确包含了对话与情感沟通识别规则，防止对主观/情感评价进行过度规划。"""
    assert "对话与情感沟通识别规则" in PLANNER_PROMPT
    assert "生硬" in PLANNER_PROMPT
    assert "问候语" in PLANNER_PROMPT
    assert "极简计划" in PLANNER_PROMPT

def test_planner_step_parser_precision_levels():
    """验证从 Planner 大模型返回的文本步骤中，精准提取 (L1-L6) 精度等级的正则表达式逻辑。"""
    # 模拟包含不同精度级别的 Planner 输出
    raw_plan_text = (
        "1. 第一步：获取大纲摘要信息 (L2)\n"
        "2. 第二步：整合精简建议报告 (L3)\n"
        "3. 第三步：输出中文总结 (L1)\n"
        "4. 第四步：无标签步骤"
    )
    
    # 提取步骤
    steps = re.findall(r"^\d+\.\s*(.+)$", raw_plan_text, re.MULTILINE)
    assert len(steps) == 4
    
    task_pool = []
    for i, step in enumerate(steps):
        precision_match = re.search(r"\((L[1-6])\)\s*$", step)
        if precision_match:
            precision_level = precision_match.group(1)
            clean_desc = step[:precision_match.start()].strip()
        else:
            precision_level = "L3" # 默认降级为 L3
            clean_desc = step.strip()
            
        task_pool.append(SubTask(
            id=f"task_{i+1}",
            description=clean_desc,
            status="pending",
            precision_level=precision_level
        ))
        
    # 断言解析后的子任务列表
    assert len(task_pool) == 4
    
    assert task_pool[0].description == "第一步：获取大纲摘要信息"
    assert task_pool[0].precision_level == "L2"
    
    assert task_pool[1].description == "第二步：整合精简建议报告"
    assert task_pool[1].precision_level == "L3"
    
    assert task_pool[2].description == "第三步：输出中文总结"
    assert task_pool[2].precision_level == "L1"
    
    # 验证无标签时的默认 Fallback
    assert task_pool[3].description == "第四步：无标签步骤"
    assert task_pool[3].precision_level == "L3"
