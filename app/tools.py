import subprocess
import os
from typing import Dict, Any, List

# 工具执行的工作目录 (Docker 内部挂载点)
# 这是 Agent 的“沙箱”边界，所有文件操作默认都发生在这里。
WORKSPACE_DIR = "/app/data"

def run_terminal_command(command: str) -> str:
    """
    在沙箱环境中执行终端命令。
    Tars 可以利用这个工具运行 shell 脚本、安装包或执行复杂的系统操作。
    """
    try:
        # 使用 subprocess 执行命令，限制在 WORKSPACE_DIR 目录下执行
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True, # 捕获 stdout 和 stderr
            text=True,           # 以文本模式读取输出
            timeout=30           # 30秒超时，防止 Agent 运行一个阻塞指令导致系统卡死
        )
        output = result.stdout
        error = result.stderr
        
        if result.returncode == 0:
            return output if output else "命令执行成功，无输出。"
        else:
            # 如果退出码不为 0，则返回错误详情供模型分析原因
            return f"错误 (退出码 {result.returncode}):\n{error}"
    except Exception as e:
        return f"执行异常: {str(e)}"

def read_file(file_path: str) -> str:
    """
    读取工作空间内指定文件的文本内容。
    """
    try:
        # 安全检查：目前仅提取文件名，防止 ../../ 类型的路径穿越攻击
        # 在 MVP 阶段通过 os.path.basename 强制限制在当前层级
        safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(file_path))
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """
    向工作空间写入文件内容。如果文件不存在则创建，存在则覆盖。
    """
    try:
        # 同样使用 basename 确保安全性
        safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(file_path))
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入到 {file_path}"
    except Exception as e:
        return f"写入失败: {str(e)}"

def list_files(directory: str = ".") -> str:
    """
    列出目录下的文件和文件夹结构，帮助 Agent 了解当前环境。
    """
    try:
        # 拼接目标路径
        safe_path = os.path.join(WORKSPACE_DIR, directory)
        files = os.listdir(safe_path)
        return "\n".join(files) if files else "目录为空。"
    except Exception as e:
        return f"列出目录失败: {str(e)}"

from app.skills import DYNAMIC_SKILL_TOOLS, execute_skill_module

# --- Tier 1: 基础系统工具 (Base Tools) ---
TIER1_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "[Tier 1] 在终端执行 shell 命令。用于基础系统维护和简单抓取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的完整命令字符串"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "[Tier 1] 读取文件的文本内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件名"}
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "[Tier 1] 写入文件内容。也可用于手动‘安装’一个新技能脚本到 skills/ 目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "文件名"},
                    "content": {"type": "string", "description": "要写入的内容"}
                },
                "required": ["file_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "[Tier 1] 列出目录下的文件列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "子目录路径"}
                }
            }
        }
    }
]

# --- 自动整合 Tier 1 和动态加载的 Tier 2 技能 ---
TOOLS = TIER1_TOOLS + DYNAMIC_SKILL_TOOLS

# 构建工具映射表
TOOL_MAP = {
    "run_terminal_command": run_terminal_command,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files
}

# 为每一个动态加载的技能创建执行闭包
def make_skill_executor(name):
    return lambda **kwargs: execute_skill_module(name, **kwargs)

for skill_def in DYNAMIC_SKILL_TOOLS:
    skill_name = skill_def["function"]["name"]
    TOOL_MAP[skill_name] = make_skill_executor(skill_name)
