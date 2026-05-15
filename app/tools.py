import subprocess
import os
from typing import Dict, Any, List

# 工具执行的工作目录 (优先从环境变量读取，默认为相对路径 data)
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "data")

def get_safe_path(relative_path: str) -> str:
    """
    安全路径解析：确保所有文件操作都被限制在 WORKSPACE_DIR 内，
    同时支持子目录结构。
    """
    # 获取绝对路径并规范化
    base_abs = os.path.abspath(WORKSPACE_DIR)
    # 处理可能的绝对路径输入，将其视为相对于工作区的路径
    if os.path.isabs(relative_path):
        # 移除开头的斜杠
        relative_path = relative_path.lstrip(os.path.sep)
    
    target_abs = os.path.normpath(os.path.join(base_abs, relative_path))
    
    # 安全性检查：目标路径必须以工作区绝对路径开头
    if not target_abs.startswith(base_abs):
        raise PermissionError(f"访问拒绝: 路径 {relative_path} 超出了工作区范围")
    
    return target_abs

def run_terminal_command(command: str) -> str:
    """
    在沙箱环境中执行终端命令。
    Tars 可以利用这个工具运行 shell 脚本、安装包或执行复杂的系统操作。
    """
    try:
        # 确保工作目录存在
        if not os.path.exists(WORKSPACE_DIR):
            os.makedirs(WORKSPACE_DIR, exist_ok=True)
            
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
    读取工作空间内指定文件的文本内容（支持子目录）。
    """
    try:
        safe_path = get_safe_path(file_path)
        if not os.path.isfile(safe_path):
            return f"读取失败: {file_path} 不是一个文件或不存在"
            
        with open(safe_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """
    向工作空间写入文件内容。支持自动创建子目录。
    """
    try:
        safe_path = get_safe_path(file_path)
        
        # 自动创建父目录
        parent_dir = os.path.dirname(safe_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入到 {file_path}"
    except Exception as e:
        return f"写入失败: {str(e)}"

def list_files(directory: str = ".") -> str:
    """
    列出目录下的文件和文件夹结构（支持子目录）。
    """
    try:
        safe_path = get_safe_path(directory)
        if not os.path.isdir(safe_path):
            return f"列出目录失败: {directory} 不是一个目录或不存在"
            
        files = os.listdir(safe_path)
        # 简单过滤，隐藏系统文件
        files = [f for f in files if not f.startswith('.')]
        return "\n".join(files) if files else "目录为空。"
    except Exception as e:
        return f"列出目录失败: {str(e)}"

from litellm import embedding
from app.db import engine, KnowledgeBase, Session, select
from sqlalchemy import text

def memory_save(content: str) -> str:
    """
    [Tier 1] 将重要信息永久存入 Tars 的长期记忆库中。
    """
    try:
        model = os.getenv("EMBEDDING_MODEL", "gemini/text-embedding-004")
        # 生成向量
        response = embedding(
            model=model,
            input=[content]
        )
        vec = response.data[0]['embedding']
        
        # 存入数据库
        with Session(engine) as session:
            new_kb = KnowledgeBase(content=content, embedding=vec)
            session.add(new_kb)
            session.commit()
        return f"记忆成功保存。内容摘要: {content[:30]}..."
    except Exception as e:
        return f"记忆保存失败: {str(e)}"

def memory_search(query: str, top_k: int = 3) -> str:
    """
    [Tier 1] 在长期记忆库中搜索相关内容。
    """
    try:
        model = os.getenv("EMBEDDING_MODEL", "gemini/text-embedding-004")
        # 生成查询向量
        response = embedding(
            model=model,
            input=[query]
        )
        query_vec = response.data[0]['embedding']
        
        # 使用 PGVector 进行相似度搜索 (L2 距离)
        with Session(engine) as session:
            # SQLModel 对原生向量操作符支持较复杂，这里使用 text 辅助
            statement = select(KnowledgeBase).order_by(
                KnowledgeBase.embedding.l2_distance(query_vec)
            ).limit(top_k)
            
            results = session.exec(statement).all()
            
            if not results:
                return "在记忆库中未找到相关记录。"
            
            output = "找回的相关记忆:\n"
            for i, res in enumerate(results):
                output += f"[{i+1}] {res.content}\n"
            return output
    except Exception as e:
        return f"记忆搜索失败: {str(e)}"

from app.skills import DYNAMIC_SKILL_TOOLS, execute_skill_module

# --- Tier 1: 基础系统工具 (Base Tools) ---
TIER1_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "memory_save",
            "description": "[Tier 1] 永久保存一条信息到长期记忆库，用于后续检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要保存的文本内容"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "[Tier 1] 根据语义搜索长期记忆库中的相关内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题"}
                },
                "required": ["query"]
            }
        }
    },
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
    "memory_save": memory_save,
    "memory_search": memory_search,
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
