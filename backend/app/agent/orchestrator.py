"""Agent Orchestrator - v0.8+ 架构重构版
工作流:
1. 拼 context (RAG + Memory + Prompt)
2. 评估问题复杂度 (走 app.agent.routing - minimaxM3 默认)
3. 根据复杂度选模型档位 (low/medium/high) → 调对应 model
4. 流式 / 非流式 LLM 调用 + tool 循环
5. 持久化 + 返回

设计原则: 路由逻辑拆到 app/agent/routing/ 子模块
- orchestrator 只负责串联, 不管复杂度算法
- 未来换分类器 / 加新档位 不动这个文件
"""
import json
import logging
import asyncio
from typing import Dict, AsyncGenerator, Optional

from app.agent.rag import rag_engine
from app.agent.memory import MemoryManager
from app.agent.routing import get_tier_router
from app.agent.pipeline.context_builder import build_messages
from app.agent.pipeline.llm_runner import run_llm_with_tools, run_llm_stream

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(self):
        self.rag = rag_engine
        self.memory = MemoryManager()
        self.router = get_tier_router()  # 用新的 routing 模块

    # ==================== 路由辅助 ====================

    async def _route_model(
        self,
        user_message: str,
        history: list,
        deep_thinking: bool,
        force_tier: Optional[str] = None,
    ) -> dict:
        """评估复杂度 + 选模型 (走 routing 模块)
        Returns: {
            "complexity", "primary_model", "fallback_models", "tier_info",
            "classification": ClassificationResult
        }
        """
        return await self.router.classify_and_route(
            user_message=user_message,
            history=history,
            deep_thinking=deep_thinking,
            force_tier=force_tier,
        )

    # ==================== 非流式 ====================

    async def process_message(
        self,
        user_message: str,
        scenario: str = "chat",
        user_id: int = 1,
        conversation_id: int = None,
        web_search_enabled: bool = None,
        deep_thinking_enabled: bool = None,
        force_tier: Optional[str] = None,
    ) -> Dict:
        """非流式处理"""
        conv_id = self.memory.get_or_create_conversation(user_id, scenario, conversation_id)
        self.memory.maybe_update_title(conv_id, user_message)

        # 1) 拼 context (含 history, 用于路由评估)
        ctx = await build_messages(
            user_message, scenario, user_id, self.memory,
            conversation_id=conv_id,
            web_search_enabled=web_search_enabled,
            deep_thinking_enabled=deep_thinking_enabled,
        )

        # 2) 路由选模型 (走 routing 模块)
        route = await self._route_model(
            user_message,
            history=ctx["messages"][1:],
            deep_thinking=bool(ctx["dt_on"]),
            force_tier=force_tier,
        )
        cls_info = route.get("classification")
        logger.info(
            f"Route: complexity={route['complexity']}, "
            f"model={route['primary_model']}, "
            f"reason={cls_info.reason if cls_info else ''} "
            f"(classifier={cls_info.model_used if cls_info else 'n/a'})"
        )

        # 3) 调 LLM (用路由选出的模型)
        # v0.8.0: deep_thinking 走深推模型链 (DeepSeek R1 / Qwen), 这些不支持 vision
        #   如果 messages 里含 inline image_url, 会 404 整个深推链路
        #   所以深推时重新拼一份 text-only messages (用 vision 描述)
        from app.agent.pipeline.preprocessor import build_user_content
        if ctx["dt_on"] and _has_inline_image(ctx["messages"]):
            logger.info("deep_thinking: stripping inline image from messages (not supported)")
            dt_messages = await _build_text_only_messages(ctx, user_message, user_id)
        else:
            dt_messages = ctx["messages"]
        result = await run_llm_with_tools(
            dt_messages,
            deep_thinking=ctx["dt_on"],
            primary_model=route["primary_model"],
            fallback_models=route["fallback_models"],
        )

        # 4) 持久化
        self.memory.save_message(conv_id, "user", user_message)
        self.memory.save_message(
            conv_id, "assistant", result["content"],
            tool_calls=json.dumps(result["tool_calls"], ensure_ascii=False) if result["tool_calls"] else None,
        )

        return {
            "conversation_id": conv_id,
            "content": result["content"],
            "reasoning": result["reasoning"],
            "tool_calls": result["tool_calls"],
            "rag_used": ctx["rag_summary"],
            "route": {
                "complexity": route["complexity"],
                "model": result.get("model_used", route["primary_model"]),
                "tier_description": route["tier_info"].description,
                "reason": cls_info.reason if cls_info else "",
                "fallback": cls_info.fallback if cls_info else False,
                "classifier_model": cls_info.model_used if cls_info else "n/a",
            },
        }

    # ==================== 流式 ====================

    async def process_message_stream(
        self,
        user_message: str,
        scenario: str = "chat",
        user_id: int = 1,
        conversation_id: int = None,
        web_search_enabled: bool = None,
        deep_thinking_enabled: bool = None,
        force_tier: Optional[str] = None,
        stop_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[str, None]:
        """流式处理 - SSE 增量输出"""
        conv_id = self.memory.get_or_create_conversation(user_id, scenario, conversation_id)
        self.memory.maybe_update_title(conv_id, user_message)

        # 1) 拼 context
        ctx = await build_messages(
            user_message, scenario, user_id, self.memory,
            conversation_id=conv_id,
            web_search_enabled=web_search_enabled,
            deep_thinking_enabled=deep_thinking_enabled,
        )

        # 2) 路由选模型 (走 routing 模块)
        route = await self._route_model(
            user_message,
            history=ctx["messages"][1:],
            deep_thinking=bool(ctx["dt_on"]),
            force_tier=force_tier,
        )
        cls_info = route.get("classification")
        logger.info(
            f"Route: complexity={route['complexity']}, "
            f"model={route['primary_model']} "
            f"(classifier={cls_info.model_used if cls_info else 'n/a'})"
        )

        # 3) 先发 RAG summary
        yield f"[RAG]{json.dumps(ctx['rag_summary'], ensure_ascii=False)}[/RAG]\n\n"

        # 4) 发路由信息
        route_info = {
            "complexity": route["complexity"],
            "model": route["primary_model"],
            "tier_description": route["tier_info"].description,
            "reason": cls_info.reason if cls_info else "",
            "fallback": cls_info.fallback if cls_info else False,
            "classifier_model": cls_info.model_used if cls_info else "n/a",
        }
        yield f"[ROUTE]{json.dumps(route_info, ensure_ascii=False)}[/ROUTE]\n\n"

        # 5) 流式 LLM
        full_content = ""
        reasoning_text = ""
        # v0.8.0: 深推时去掉 inline 图
        from app.agent.pipeline.preprocessor import build_user_content
        if ctx["dt_on"] and _has_inline_image(ctx["messages"]):
            logger.info("deep_thinking stream: stripping inline image from messages")
            dt_messages = await _build_text_only_messages(ctx, user_message, user_id)
        else:
            dt_messages = ctx["messages"]
        async for ev_type, ev_data in run_llm_stream(
            dt_messages,
            deep_thinking=ctx["dt_on"],
            primary_model=route["primary_model"],
            fallback_models=route["fallback_models"],
            stop_event=stop_event,
        ):
            if ev_type == "reasoning":
                reasoning_text += ev_data
                yield f"[THINKING]{ev_data}[/THINKING]\n\n"
            elif ev_type == "tool_call":
                yield f"[TOOL_CALLS]{json.dumps(ev_data, ensure_ascii=False)}[/TOOL_CALLS]\n\n"
            elif ev_type == "tool_result":
                yield f"[TOOL_RESULTS]{json.dumps(ev_data, ensure_ascii=False)}[/TOOL_RESULTS]\n\n"
            elif ev_type == "content":
                full_content += ev_data
                yield ev_data
            elif ev_type == "done":
                full_content = ev_data["content"]
                if ev_data["reasoning"] and not reasoning_text:
                    reasoning_text = ev_data["reasoning"]
                if ev_data.get("model_used"):
                    route_info["model"] = ev_data["model_used"]

        # 6) 最后发 REASONING
        if reasoning_text and not full_content.lstrip().startswith("["):
            yield f"[REASONING]{json.dumps({'thinking': reasoning_text, 'answer': full_content, 'route': route_info}, ensure_ascii=False)}[/REASONING]\n\n"

        # 7) 持久化
        self.memory.save_message(conv_id, "user", user_message)
        self.memory.save_message(conv_id, "assistant", full_content, tool_calls="[]")


orchestrator = AgentOrchestrator()


# ===== v0.8.0: Deep thinking 专用 helpers =====

def _has_inline_image(messages: list) -> bool:
    """检测 messages 中是否含 inline image_url (多模态格式)
    深推模型 (DeepSeek R1 / Qwen) 不支持 vision, 要重拼 text-only messages
    """
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


async def _build_text_only_messages(ctx: dict, user_message: str, user_id: int) -> list:
    """重拼一份不含 inline image 的 messages, 给深推用
    - 只调一次 vision_client 描述图, 不重复
    - user content 改为纯文本 + 图片描述
    """
    from app.agent.pipeline.preprocessor import build_user_content
    # 从 ctx 里拿出 top_resource
    top_resource = (ctx.get("user_resources") or [None])[0]
    user_content = await build_user_content(
        user_message,
        top_resource=top_resource,
        include_image=False,  # 强制不送 inline 图
        for_deep_thinking=True,
    )
    # 重建 messages: system + history + text-only user
    history = ctx["messages"][1:-1]  # 除 system 和最后一 user
    return [ctx["messages"][0]] + history + [user_content]
