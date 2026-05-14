import subprocess
import os
from typing import Dict, Any, List

# 工具执行的工作目录 (Docker 内部挂载点)
WORKSPACE_DIR = "/app/data"

def run_terminal_command(command: str) -> str:
    """执行终端命令并返回结果。"""
    try:
        # 使用 subprocess 执行命令，限制在 WORKSPACE_DIR
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout
        error = result.stderr
        
        if result.returncode == 0:
            return output if output else "命令执行成功，无输出。"
        else:
            return f"错误 (退出码 {result.returncode}):\n{error}"
    except Exception as e:
        return f"执行异常: {str(e)}"

def read_file(file_path: str) -> str:
    """读取文件内容。"""
    try:
        # 安全检查：防止路径穿越 (MVP 阶段简单处理，实际应更严格)
        safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(file_path))
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """写入文件内容。"""
    try:
        safe_path = os.path.join(WORKSPACE_DIR, os.path.basename(file_path))
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入到 {file_path}"
    except Exception as e:
        return f"写入失败: {str(e)}"

def list_files(directory: str = ".") -> str:
    """列出目录下的文件。"""
    try:
        safe_path = os.path.join(WORKSPACE_DIR, directory)
        files = os.listdir(safe_path)
        return "\n".join(files) if files else "目录为空。"
    except Exception as e:
        return f"列出目录失败: {str(e)}"

# 定义工具元数据 (OpenAI 格式)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "在终端执行 shell 命令。例如: 'ls -la', 'python script.py'。",
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
            "description": "读取指定文件的内容。",
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
            "description": "向指定文件写入内容。",
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
            "description": "列出当前工作目录或子目录下的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "子目录路径，默认为 '.'"}
                }
            }
        }
    }
]

# 工具映射表
TOOL_MAP = {
    "run_terminal_command": run_terminal_command,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files
}
