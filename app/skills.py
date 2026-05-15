import os
import json
import subprocess
from typing import List, Dict, Any

# 技能存储的根目录
SKILLS_DIR = "/app/skills"

def load_modular_skills() -> List[Dict[str, Any]]:
    """
    扫描 SKILLS_DIR 下的子目录，读取 skill.json 并生成模型可用的工具列表。
    """
    tool_definitions = []
    if not os.path.exists(SKILLS_DIR):
        os.makedirs(SKILLS_DIR, exist_ok=True)
        return []

    for folder in os.listdir(SKILLS_DIR):
        folder_path = os.path.join(SKILLS_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
            
        manifest_path = os.path.join(folder_path, "manifests", "skill.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                # 构建符合 OpenAI/LiteLLM 标准的工具定义
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": manifest["name"],
                        "description": f"[Tier 2 Skill] {manifest['description']}",
                        "parameters": manifest.get("parameters", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                }
                tool_definitions.append(tool_def)
            except Exception as e:
                print(f"警告: 加载技能 {folder} 失败: {str(e)}")
                
    return tool_definitions

def execute_skill_module(skill_name: str, **kwargs) -> str:
    """
    执行模块化技能。通过命令行将参数传递给 src/executor.py。
    """
    skill_folder = os.path.join(SKILLS_DIR, skill_name)
    executor_path = os.path.join(skill_folder, "src", "executor.py")
    
    if not os.path.exists(executor_path):
        return f"错误: 未找到技能 {skill_name} 的执行逻辑。"

    try:
        # 将 kwargs 转换为 JSON 字符串作为参数传递
        args_json = json.dumps(kwargs)
        cmd = ["python", executor_path, args_json]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"技能执行失败: {result.stderr}"
    except Exception as e:
        return f"执行异常: {str(e)}"

# --- 动态生成工具集 ---
# 这样我们就不用在 tools.py 里手动添加每个技能了
DYNAMIC_SKILL_TOOLS = load_modular_skills()

# 统一的执行映射
def skill_executor_wrapper(**kwargs):
    # 这个 wrapper 会被绑定到所有动态加载的技能名上
    # 我们需要在调用时知道是哪个技能，稍微有点复杂，我们在 tools.py 处理
    pass
