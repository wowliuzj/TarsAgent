import os
import sys
import json
import subprocess
from typing import List, Optional
from mcp.server.fastmcp import FastMCP
from litellm import embedding
from sqlmodel import Session, select, text

# 将项目根目录加入 sys.path 以便导入 app 中的模块
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.append(PROJECT_ROOT)

from app.db import engine, KnowledgeBase
from app.logger import logger

# --- 核心配置 ---
SENSITIVE_FILES = {".env", ".git", "env_example", "id_rsa", "config.json"}

# --- 工具逻辑 ---

def is_sensitive(path: str) -> bool:
    parts = path.split(os.sep)
    return any(p in SENSITIVE_FILES for p in parts)

def resolve_path(target_path: str) -> str:
    if os.path.isabs(target_path):
        abs_path = os.path.normpath(target_path)
    else:
        abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, target_path))
    if is_sensitive(abs_path):
        raise PermissionError(f"安全限制: 禁止访问敏感路径 {target_path}")
    return abs_path

# --- 创建 FastMCP 实例 ---
mcp = FastMCP("system_runtime")

@mcp.tool()
def read_file(file_path: str) -> str:
    """读取文件的文本内容。支持相对项目根目录的路径。"""
    try:
        abs_path = resolve_path(file_path)
        if not os.path.isfile(abs_path):
            return f"读取失败: {file_path} 不存在"
        with open(abs_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {str(e)}"

@mcp.tool()
def write_file(file_path: str, content: str) -> str:
    """写入文件内容。"""
    try:
        abs_path = resolve_path(file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"成功写入到 {file_path}"
    except Exception as e:
        return f"写入失败: {str(e)}"

@mcp.tool()
def list_files(directory: str = ".") -> str:
    """列出目录内容。"""
    try:
        abs_path = resolve_path(directory)
        if not os.path.isdir(abs_path):
            return f"错误: {directory} 不是目录"
        files = [f for f in os.listdir(abs_path) if not f.startswith('.') and f not in SENSITIVE_FILES]
        return "\n".join(files) if files else "目录为空。"
    except Exception as e:
        return f"列出目录失败: {str(e)}"

@mcp.tool()
def run_terminal_command(command: str) -> str:
    """在 Tars 专用工作区目录下执行终端命令，避免污染项目根目录。"""
    try:
        # 获取配置的工作区目录，默认为 "data"
        workspace_env = os.getenv("WORKSPACE_DIR", "data")
        workspace_path = os.path.abspath(os.path.join(PROJECT_ROOT, workspace_env, "workspace"))
        
        # 确保 data/workspace 物理文件夹存在
        os.makedirs(workspace_path, exist_ok=True)
        
        result = subprocess.run(command, shell=True, cwd=workspace_path, capture_output=True, text=True, timeout=60)
        return result.stdout if result.returncode == 0 else f"错误 (退出码 {result.returncode}): {result.stderr}"
    except Exception as e:
        return f"执行异常: {str(e)}"

@mcp.tool()
def memory_save(content: str) -> str:
    """永久保存一条信息到长期记忆库。"""
    try:
        model = os.getenv("EMBEDDING_MODEL")
        response = embedding(model=model, input=[content])
        vec = response.data[0]['embedding']
        with Session(engine) as session:
            new_kb = KnowledgeBase(content=content, embedding=vec)
            session.add(new_kb)
            session.commit()
        return f"记忆成功保存: {content[:30]}..."
    except Exception as e:
        return f"记忆保存失败: {str(e)}"

@mcp.tool()
def memory_search(query: str, top_k: int = 3) -> str:
    """根据语义搜索长期记忆库中的相关内容。"""
    try:
        model = os.getenv("EMBEDDING_MODEL")
        response = embedding(model=model, input=[query])
        query_vec = response.data[0]['embedding']
        with Session(engine) as session:
            statement = select(KnowledgeBase).order_by(KnowledgeBase.embedding.l2_distance(query_vec)).limit(top_k)
            results = session.exec(statement).all()
            if not results: return "在记忆库中未找到相关记录。"
            output = "找回的相关记忆:\n"
            for i, res in enumerate(results):
                output += f"[{i+1}] {res.content}\n"
            return output
    except Exception as e:
        return f"记忆搜索失败: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
