import os
import json
import subprocess
import sys
from typing import List, Dict, Any

# 技能存储的根目录
SKILLS_DIR = "/app/skills"

def install_skill_dependencies(skill_path: str):
    """如果技能目录下存在 requirements.txt，则尝试安装依赖。"""
    req_path = os.path.join(skill_path, "requirements.txt")
    if os.path.exists(req_path):
        try:
            # 使用当前运行环境的 pip 进行安装
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path], 
                                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        except Exception as e:
            print(f"警告: 技能 {skill_path} 依赖安装失败: {e}")

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
            
        # 安装依赖
        install_skill_dependencies(folder_path)

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
    执行模块化技能。根据 skill.json 声明的 runtime 和 entry 执行对应脚本。
    """
    skill_folder = os.path.join(SKILLS_DIR, skill_name)
    manifest_path = os.path.join(skill_folder, "manifests", "skill.json")
    
    if not os.path.exists(manifest_path):
        return f"错误: 未找到技能 {skill_name} 的声明文件。"

    try:
        # 1. 读取声明以获取运行配置
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        # 优先使用 main (类似 package.json)，兼容 entry 和默认值
        runtime = manifest.get("runtime", "python")
        entry_point = manifest.get("main") or manifest.get("entry", "src/executor.py")
        full_entry_path = os.path.join(skill_folder, entry_point)

        if not os.path.exists(full_entry_path):
            return f"错误: 技能 {skill_name} 缺少入口文件 {entry_point}"

        # 2. 准备执行命令
        args_json = json.dumps(kwargs)
        if runtime == "python":
            cmd = [sys.executable, full_entry_path, args_json]
        elif runtime == "node":
            cmd = ["node", full_entry_path, args_json]
        elif runtime == "shell" or runtime == "bash":
            cmd = ["bash", full_entry_path, args_json]
        else:
            return f"错误: 不支持的运行环境 {runtime}"

        # 3. 执行并捕获结果
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"技能执行失败 (Exit {result.returncode}): {result.stderr or result.stdout}"
            
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
