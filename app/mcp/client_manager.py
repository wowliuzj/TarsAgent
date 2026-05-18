import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from app.logger import logger
from contextlib import AsyncExitStack

class MCPClientManager:
    def __init__(self, servers_dir: str = "mcp_servers"):
        self.servers_dir = os.path.abspath(servers_dir)
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_session: Dict[str, str] = {} # tool_name -> server_name
        self.server_configs: Dict[str, Dict] = {} # server_name -> {path, manifest}
        self.exit_stack = AsyncExitStack()
        self.all_tools = []

    async def start(self):
        """扫描目录并发现所有 MCP Servers (仅加载元数据，不启动容器)"""
        if not os.path.exists(self.servers_dir):
            os.makedirs(self.servers_dir, exist_ok=True)
            return

        for server_name in os.listdir(self.servers_dir):
            server_path = os.path.join(self.servers_dir, server_name)
            if not os.path.isdir(server_path): continue
            
            manifest_path = os.path.join(server_path, "manifests", "server.json")
            if not os.path.exists(manifest_path):
                manifest_path = os.path.join(server_path, "server.json")
            
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    
                    self.server_configs[server_name] = {
                        "path": server_path,
                        "manifest": manifest
                    }
                    
                    # 尝试从缓存加载工具定义，如果没缓存则启动一次来获取
                    await self._discover_tools(server_name)
                except Exception as e:
                    logger.error(f"发现 MCP Server {server_name} 失败: {str(e)}")

    async def _discover_tools(self, server_name: str):
        """发现工具定义。优先使用缓存文件以避免启动容器。"""
        cfg = self.server_configs[server_name]
        cache_path = os.path.join(cfg["path"], "tools_metadata.json")
        
        tools = []
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    tools = json.load(f)
            except:
                tools = []

        if not tools:
            # 首次运行，必须启动一次来获取工具定义
            logger.info(f"首次加载 {server_name}，正在生成工具元数据缓存...")
            await self._connect_server(server_name)
            session = self.sessions[server_name]
            tools_resp = await session.list_tools()
            tools = []
            for t in tools_resp.tools:
                tools.append({
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema
                })
            # 写入缓存
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(tools, f, ensure_ascii=False, indent=2)
        
        for tool in tools:
            self.tool_to_session[tool["name"]] = server_name
            self.all_tools.append({
                "type": "function",
                "function": tool
            })

        # 同步工具索引到数据库中以便进行 RAG 检索
        try:
            from sqlmodel import Session, select
            from app.db import engine, MCPToolIndex
            from litellm import embedding
            from datetime import datetime
            
            with Session(engine) as db_sess:
                # 获取数据库中该 server 现有的所有工具
                statement = select(MCPToolIndex).where(MCPToolIndex.server_name == server_name)
                db_tools = db_sess.exec(statement).all()
                db_tool_map = {t.tool_name: t for t in db_tools}
                
                for t in tools:
                    t_name = t["name"]
                    t_desc = t["description"] or ""
                    text_to_embed = f"Tool Name: {t_name}\nDescription: {t_desc}"
                    
                    # 如果工具在数据库中不存在，或者描述有改变，就计算 Embedding 并写入/更新
                    if t_name not in db_tool_map or db_tool_map[t_name].description != t_desc:
                        logger.info(f"正在为工具 {server_name}.{t_name} 计算语义向量并同步到 DB...")
                        model = os.getenv("EMBEDDING_MODEL")
                        response = embedding(model=model, input=[text_to_embed])
                        vec = response.data[0]['embedding']
                        
                        if t_name in db_tool_map:
                            db_tool = db_tool_map[t_name]
                            db_tool.description = t_desc
                            db_tool.embedding = vec
                            db_tool.tool_schema = t
                            db_tool.updated_at = datetime.utcnow()
                            db_sess.add(db_tool)
                        else:
                            new_tool = MCPToolIndex(
                                server_name=server_name,
                                tool_name=t_name,
                                description=t_desc,
                                embedding=vec,
                                tool_schema=t
                            )
                            db_sess.add(new_tool)
                
                db_sess.commit()
        except Exception as e:
            logger.error(f"同步 MCP Server {server_name} 工具元数据到数据库失败: {str(e)}")

    async def get_tools_for_query(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        根据用户查询 Query，采用 Tool RAG 动态筛选并召回工具。
        - 核心基础设施工具 (system_runtime, web_search) 默认 100% 注入。
        - 领域特种工具 (如 crypto_market) 通过 pgvector 检索 Top-K 相关度注入。
        """
        core_servers = {"system_runtime", "web_search"}
        
        try:
            from sqlmodel import Session, select
            from app.db import engine, MCPToolIndex
            from litellm import embedding
            
            core_tools = []
            special_tools = []
            
            with Session(engine) as db_sess:
                # 1. 核心工具直接查询并加载
                core_stmt = select(MCPToolIndex).where(MCPToolIndex.server_name.in_(core_servers))
                db_core_tools = db_sess.exec(core_stmt).all()
                for ct in db_core_tools:
                    core_tools.append({
                        "type": "function",
                        "function": ct.tool_schema
                    })
                
                # 2. 对非核心领域的特种工具，计算用户 Query 的 Embedding 并执行向量搜索检索
                non_core_count_stmt = select(MCPToolIndex).where(
                    ~MCPToolIndex.server_name.in_(core_servers)
                )
                non_core_tools_exist = db_sess.exec(non_core_count_stmt).first()
                
                if non_core_tools_exist:
                    logger.info(f"正在为 Query '{query[:30]}...' 执行 Tool RAG 检索...")
                    model = os.getenv("EMBEDDING_MODEL")
                    response = await asyncio.to_thread(
                        embedding,
                        model=model,
                        input=[query]
                    )
                    query_vec = response.data[0]['embedding']
                    
                    # 根据 L2 距离召回非核心特种工具
                    rag_stmt = select(MCPToolIndex).where(
                        ~MCPToolIndex.server_name.in_(core_servers)
                    ).order_by(
                        MCPToolIndex.embedding.l2_distance(query_vec)
                    ).limit(top_k)
                    
                    db_special_tools = db_sess.exec(rag_stmt).all()
                    for st in db_special_tools:
                        logger.info(f"Tool RAG 命中特种工具: {st.server_name}.{st.tool_name}")
                        special_tools.append({
                            "type": "function",
                            "function": st.tool_schema
                        })
            
            logger.info(f"Tool RAG 组装完成: 核心工具 {len(core_tools)} 个, 特种工具 {len(special_tools)} 个")
            return core_tools + special_tools
            
        except Exception as e:
            logger.error(f"执行 Tool RAG 检索失败: {str(e)}")
            return self.all_tools

    async def _connect_server(self, server_name: str):
        """物理启动 MCP Server 进程/容器"""
        if server_name in self.sessions:
            return

        cfg = self.server_configs[server_name]
        server_path = cfg["path"]
        manifest = cfg["manifest"]

        runtime_cfg = manifest.get("runtime", {"type": "native"})
        runtime_type = runtime_cfg.get("type", "native")
        entrypoint = manifest.get("entrypoint", "python src/server.py")
        
        # 启动日志提示
        logger.info(f"⏳ [工具环境准备中] 正在启动 {server_name} ({runtime_type})...")

        cmd_parts = entrypoint.split()
        if runtime_type == "docker":
            image = runtime_cfg.get("image", "python:3.10-slim")
            docker_args = [
                "run", "-i", "--rm",
                "--add-host", "host.docker.internal:host-gateway",
                "-v", f"{server_path}:/app",
                "-v", "tars_mcp_venv:/usr/local/lib/python3.10/site-packages",
                "-w", "/app"
            ]
            
            passthrough_vars = [
                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", 
                "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                "TAVILY_API_KEY", "OPENAI_API_KEY", "MODEL_NAME"
            ]
            env_to_pass = os.environ.copy()
            for var in passthrough_vars:
                val = env_to_pass.get(var)
                if val:
                    val = val.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
                    docker_args.extend(["-e", f"{var}={val}"])

            inner_cmd = entrypoint
            if os.path.exists(os.path.join(server_path, "requirements.txt")):
                with open(os.path.join(server_path, "requirements.txt"), "r") as f:
                    reqs = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                check_script = "; ".join([f"import {r.split('==')[0].split('>=')[0].replace('-', '_')}" for r in reqs])
                inner_cmd = f"python3 -c '{check_script}' 2>/dev/null || (pip install -q --no-cache-dir -r requirements.txt > /dev/null 2>&1) && {entrypoint}"
            
            docker_args.append(image)
            docker_args.extend(["sh", "-c", inner_cmd])
            server_params = StdioServerParameters(command="docker", args=docker_args, env=os.environ.copy())
        else:
            server_params = StdioServerParameters(command=cmd_parts[0], args=cmd_parts[1:], env=os.environ.copy(), cwd=server_path)

        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self.sessions[server_name] = session

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        server_name = self.tool_to_session.get(tool_name)
        if not server_name:
            return f"错误: 未找到工具 {tool_name}"
        
        # [按需启动核心]
        if server_name not in self.sessions:
            await self._connect_server(server_name)
        
        session = self.sessions[server_name]
        try:
            result = await session.call_tool(tool_name, arguments)
            if result.content and len(result.content) > 0:
                return result.content[0].text
            return "工具执行成功，但无返回内容。"
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {str(e)}")
            return f"工具执行异常: {str(e)}"

    async def stop(self):
        """安全关闭所有 MCP 连接"""
        logger.info("正在关闭所有 MCP 服务...")
        try:
            # 1. 先清空会话映射
            self.sessions.clear()
            # 2. 释放 ExitStack 中的所有资源 (包括 stdio_client 和任务组)
            await self.exit_stack.aclose()
        except Exception as e:
            logger.debug(f"MCP 关闭期间捕获到预期内的异步清理异常: {e}")
        
        logger.info("所有 MCP 服务已安全关闭。")
