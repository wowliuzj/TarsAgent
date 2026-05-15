import subprocess
import os
from typing import Dict, Any, List

# 项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 敏感文件黑名单，禁止 Tars 读取或列出
SENSITIVE_FILES = {".env", ".git", "env_example", "id_rsa", "config.json"}

def is_sensitive(path: str) -> bool:
    """
    检查路径是否包含敏感文件或目录。
    """
    parts = path.split(os.sep)
    return any(p in SENSITIVE_FILES for p in parts)

def resolve_path(target_path: str) -> str:
    """
    将路径解析为绝对路径。如果是相对路径，则相对于项目根目录。
    """
    if os.path.isabs(target_path):
        abs_path = os.path.normpath(target_path)
    else:
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, target_path))
    
    # 虽然取消了工作区限制，但我们依然禁止访问敏感配置文件
    if is_sensitive(abs_path):
        raise PermissionError(f"安全限制: 禁止访问敏感路径 {target_path}")
        
    return abs_path

def run_terminal_command(command: str) -> str:
    """
    在项目根目录下执行终端命令。
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return result.stdout if result.stdout else "命令执行成功，无输出。"
        else:
            return f"错误 (退出码 {result.returncode}):\n{result.stderr}"
    except Exception as e:
        return f"执行异常: {str(e)}"

def read_file(file_path: str) -> str:
    """
    读取文件内容。支持绝对路径或相对于项目根目录的路径。
    """
    try:
        abs_path = resolve_path(file_path)
        if not os.path.isfile(abs_path):
            return f"读取失败: {file_path} 不存在或不是文件"
            
        with open(abs_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

def write_file(file_path: str, content: str) -> str:
    """
    写入文件内容。
    """
    try:
        abs_path = resolve_path(file_path)
        parent_dir = os.path.dirname(abs_path)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入到 {file_path}"
    except Exception as e:
        return f"写入失败: {str(e)}"

def list_files(directory: str = ".") -> str:
    """
    列出目录内容。
    """
    try:
        abs_path = resolve_path(directory)
        if not os.path.isdir(abs_path):
            return f"错误: {directory} 不是目录"
            
        files = os.listdir(abs_path)
        # 过滤系统文件和黑名单敏感文件
        files = [f for f in files if not f.startswith('.') and f not in SENSITIVE_FILES]
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
        model = os.getenv("EMBEDDING_MODEL")
        if not model:
            raise ValueError("错误: 未在环境变量中找到 EMBEDDING_MODEL。")
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
        model = os.getenv("EMBEDDING_MODEL")
        if not model:
            raise ValueError("错误: 未在环境变量中找到 EMBEDDING_MODEL。")
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
    return lambda **kwargs: execute_skill_module(name, kwargs)

for skill_def in DYNAMIC_SKILL_TOOLS:
    skill_name = skill_def["function"]["name"]
    TOOL_MAP[skill_name] = make_skill_executor(skill_name)
