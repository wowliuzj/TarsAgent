import os
import json
import uuid
import asyncio
import random
from typing import List, Dict, Any, Optional, Type
from datetime import datetime
from pydantic import BaseModel

from app.logger import logger, append_trace_event
from app.mcp.client_manager import MCPClientManager
from app.mcp.state import TarsState, Mission, Lane, TraceEvent
from app.mcp.graph import TarsGraphBuilder
from app.tier_routing import resolve_tier_and_model
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from litellm import completion
from app.prompts import BASE_SYSTEM_PROMPT, get_dynamic_project_context

class TarsAgent:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.model = os.getenv("MODEL_NAME")
        if not self.model:
            raise ValueError("错误: 未在环境变量中找到 MODEL_NAME。")
        self._trace_token_usage: Dict[str, int] = {}
        self.last_trace_id: Optional[str] = None
        
        self.mcp_manager = MCPClientManager()
        self._mcp_initialized = False
        
        # 初始化编译后的图
        self.graph = TarsGraphBuilder(self).compile()
        logger.info("Tars 2.0 (LangGraph + THP) 引擎已就绪。")

    async def _init_mcp(self):
        """初始化并发现 MCP Servers (懒加载模式)"""
        if not self._mcp_initialized:
            await self.mcp_manager.start()
            self._mcp_initialized = True

    async def run(self, user_input: str) -> str:
        """执行 Tars 2.0 任务流"""
        await self._init_mcp()
        trace_id = str(uuid.uuid4())
        self.last_trace_id = trace_id
        self._trace_token_usage[trace_id] = 0
        
        # 获取动态项目上下文
        dynamic_context = get_dynamic_project_context()
        
        # 1. 构造初始状态 (THP 规范)
        initial_state: TarsState = {
            "mission": Mission(
                id=str(uuid.uuid4()),
                goal=user_input
            ),
            "history": [
                SystemMessage(content=BASE_SYSTEM_PROMPT + dynamic_context),
                HumanMessage(content=user_input)
            ],
            "shared_memory": {},
            "trace_id": trace_id,
            "trace_events": [],
            "task_pool": [],
            "audit_log": [],
            "current_lane": Lane.EXECUTION,
            "next_step": None,
            "current_task_index": 0,
            "executor_retries": 0,
            "planner_retries": 0,
            "audit_feedback": ""
        }
        append_trace_event(TraceEvent(
            trace_id=trace_id,
            event_id=str(uuid.uuid4()),
            ts=datetime.utcnow().isoformat() + "Z",
            node="agent",
            event_type="agent_run_started",
            payload={"session_id": self.session_id, "goal": user_input}
        ).model_dump())

        logger.info(f"🚀 启动任务泳道: {initial_state['current_lane']}")
        
        # 2. 调用图引擎 (自动处理 ReAct 循环)
        try:
            final_state = await self.graph.ainvoke(initial_state)
        except Exception as e:
            append_trace_event(TraceEvent(
                trace_id=trace_id,
                event_id=str(uuid.uuid4()),
                ts=datetime.utcnow().isoformat() + "Z",
                node="agent",
                event_type="agent_run_failed",
                severity="error",
                payload={"error": str(e)}
            ).model_dump())
            self._trace_token_usage.pop(trace_id, None)
            raise
        
        # 3. 提取最终回答
        final_response = "未能获取到回答。"
        for msg in reversed(final_state["history"]):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                content = msg.content.strip()
                import json
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and "reasoning" in data:
                        final_response = data["reasoning"]
                    else:
                        final_response = msg.content
                except Exception:
                    final_response = msg.content
                break

        append_trace_event(TraceEvent(
            trace_id=trace_id,
            event_id=str(uuid.uuid4()),
            ts=datetime.utcnow().isoformat() + "Z",
            node="agent",
            event_type="agent_run_completed",
            payload={"response_length": len(final_response)}
        ).model_dump())
        self._trace_token_usage.pop(trace_id, None)
        
        return final_response

    async def _call_model(
        self,
        messages: List[BaseMessage],
        use_tools: bool = True,
        response_format: Optional[Type[BaseModel]] = None,
        trace_id: Optional[str] = None,
        caller_node: str = "unknown",
        precision_level: Optional[str] = None,
        routing_state: Optional[Dict[str, Any]] = None,
    ) -> AIMessage:
        """适配 LiteLLM 调用并返回 AIMessage"""
        def is_transient_llm_error(exc: Exception) -> bool:
            msg = str(exc).lower()
            transient_markers = [
                "apiconnectionerror",
                "connecterror",
                "timeout",
                "temporarily unavailable",
                "connection reset",
                "unexpected eof",
                "ssl",
                "tls",
                "rate limit",
                "429",
                "503",
                "502",
                "504",
            ]
            return any(m in msg for m in transient_markers)

        llm_messages = []
        for m in messages:
            role = "user"
            if isinstance(m, SystemMessage): role = "system"
            elif isinstance(m, AIMessage): role = "assistant"
            elif isinstance(m, HumanMessage): role = "user"
            elif hasattr(m, "tool_call_id"): role = "tool"
            
            msg_dict = {"role": role, "content": str(m.content) if m.content else ""}
            
            # 处理 Assistant 的工具调用
            if role == "assistant" and isinstance(m, AIMessage) and m.tool_calls:
                llm_tool_calls = []
                for tc in m.tool_calls:
                    llm_tool_calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"])
                        }
                    })
                msg_dict["tool_calls"] = llm_tool_calls
            
            # 处理 Tool 消息的响应
            if role == "tool":
                msg_dict["tool_call_id"] = m.tool_call_id
                # 注意：LiteLLM 的 tool 角色也需要 name
                msg_dict["name"] = getattr(m, "name", "tool")
            
            llm_messages.append(msg_dict)

        # 调用 LiteLLM（含 Tiered Reasoning 路由）
        tools = self.mcp_manager.all_tools if (self.mcp_manager.all_tools and use_tools) else None
        run_tokens_used = self._trace_token_usage.get(trace_id, 0) if trace_id else 0
        tier_resolution = resolve_tier_and_model(
            default_model=self.model,
            caller_node=caller_node,
            precision_level=precision_level,
            state=routing_state,
            run_tokens_used=run_tokens_used,
        )
        
        completion_kwargs = {
            "model": tier_resolution.model,
            "messages": llm_messages,
            "tools": tools
        }
        if response_format:
            completion_kwargs["response_format"] = response_format
        
        fallback_model = os.getenv("MODEL_FALLBACK_NAME")
        model_candidates = [tier_resolution.model]
        if fallback_model and fallback_model not in model_candidates:
            model_candidates.append(fallback_model)

        max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        retry_base_delay_ms = int(os.getenv("LLM_RETRY_BASE_DELAY_MS", "800"))

        response = None
        last_err: Optional[Exception] = None
        used_model = tier_resolution.model
        if trace_id and tier_resolution.transition:
            append_trace_event(TraceEvent(
                trace_id=trace_id,
                event_id=str(uuid.uuid4()),
                ts=datetime.utcnow().isoformat() + "Z",
                node=caller_node,
                event_type="tier_transition",
                severity="warning",
                payload={
                    **tier_resolution.transition,
                    "resolved_model": tier_resolution.model,
                    "precision_level": precision_level,
                }
            ).model_dump())

        for model_idx, candidate_model in enumerate(model_candidates):
            for attempt in range(1, max_retries + 1):
                try:
                    attempt_kwargs = dict(completion_kwargs)
                    attempt_kwargs["model"] = candidate_model

                    if trace_id:
                        if model_idx > 0 and attempt == 1:
                            append_trace_event(TraceEvent(
                                trace_id=trace_id,
                                event_id=str(uuid.uuid4()),
                                ts=datetime.utcnow().isoformat() + "Z",
                                node=caller_node,
                                event_type="llm_call_fallback",
                                severity="warning",
                                payload={
                                    "from_model": model_candidates[0],
                                    "to_model": candidate_model,
                                    "reason": str(last_err)[:300] if last_err else "primary_failed",
                                }
                            ).model_dump())

                        append_trace_event(TraceEvent(
                            trace_id=trace_id,
                            event_id=str(uuid.uuid4()),
                            ts=datetime.utcnow().isoformat() + "Z",
                            node=caller_node,
                            event_type="llm_call_started",
                            payload={
                                "model": candidate_model,
                                "default_model": self.model,
                                "tier": tier_resolution.tier,
                                "base_tier": tier_resolution.base_tier,
                                "route_reason": tier_resolution.route_reason,
                                "precision_level": precision_level,
                                "use_tools": use_tools,
                                "message_count": len(llm_messages),
                                "response_format": response_format.__name__ if response_format else None,
                                "run_tokens_used_before_call": run_tokens_used,
                                "attempt": attempt,
                                "max_retries": max_retries,
                                "is_fallback_model": model_idx > 0,
                            }
                        ).model_dump())

                    response = await asyncio.to_thread(
                        completion,
                        **attempt_kwargs
                    )
                    used_model = candidate_model
                    break
                except Exception as e:
                    last_err = e
                    transient = is_transient_llm_error(e)
                    if trace_id:
                        append_trace_event(TraceEvent(
                            trace_id=trace_id,
                            event_id=str(uuid.uuid4()),
                            ts=datetime.utcnow().isoformat() + "Z",
                            node=caller_node,
                            event_type="llm_call_retry",
                            severity="warning",
                            payload={
                                "model": candidate_model,
                                "attempt": attempt,
                                "max_retries": max_retries,
                                "transient": transient,
                                "error": str(e)[:400],
                            }
                        ).model_dump())
                    if (not transient) or attempt >= max_retries:
                        break
                    delay_s = (retry_base_delay_ms / 1000.0) * (2 ** (attempt - 1)) + random.uniform(0, 0.2)
                    await asyncio.sleep(delay_s)

            if response is not None:
                break

        if response is None:
            raise last_err if last_err else RuntimeError("LLM 调用失败且无具体异常信息。")

        resp_msg = response.choices[0].message
        
        # 构造 AIMessage
        tool_calls = []
        if hasattr(resp_msg, "tool_calls") and resp_msg.tool_calls:
            for tc in resp_msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments)
                })
        
        if trace_id:
            usage = {}
            total_tokens = 0
            if hasattr(response, "usage") and response.usage:
                usage = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(response.usage, "completion_tokens", None),
                    "total_tokens": getattr(response.usage, "total_tokens", None)
                }
                total_tokens = int(getattr(response.usage, "total_tokens", 0) or 0)
            if trace_id:
                self._trace_token_usage[trace_id] = self._trace_token_usage.get(trace_id, 0) + total_tokens
            append_trace_event(TraceEvent(
                trace_id=trace_id,
                event_id=str(uuid.uuid4()),
                ts=datetime.utcnow().isoformat() + "Z",
                node=caller_node,
                event_type="llm_call_finished",
                payload={
                    "model": used_model,
                    "tier": tier_resolution.tier,
                    "route_reason": tier_resolution.route_reason,
                    "tool_calls_count": len(tool_calls),
                    "content_length": len(resp_msg.content or ""),
                    "usage": usage,
                    "run_tokens_used_after_call": self._trace_token_usage.get(trace_id, run_tokens_used)
                }
            ).model_dump())
        
        return AIMessage(content=resp_msg.content or "", tool_calls=tool_calls)

    async def shutdown(self):
        """关闭所有 MCP 连接"""
        await self.mcp_manager.stop()
