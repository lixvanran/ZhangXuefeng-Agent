"""聊天路由 - 核心接口"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.agent.orchestrator import orchestrator
from app.models.schemas import ChatRequest
import json
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["聊天"])


@router.post("")
async def chat(request: ChatRequest, fastapi_request: Request, db: Session = Depends(get_db)):
    """聊天接口（流式）"""
    # 防成本攻击: force_tier 只在 DEBUG 模式或服务端显式启用时生效
    import os
    debug_force = os.environ.get("ZHAANG_DEBUG_FORCE_TIER") == "1"
    effective_force_tier = request.force_tier if debug_force else None
    if request.stream:
        # v0.8.0: stop_event 让 LLM 流能每个 chunk 级别检查, 而不是只在 yield 之间
        # 用户按 Stop 按钮会断开 SSE, 我们的 disconnect watcher 立即 set stop_event
        stop_event = asyncio.Event()

        async def disconnect_watcher():
            """监视 SSE 断开, 断开就 set stop_event 让 LLM 流立即停"""
            while not stop_event.is_set():
                if await fastapi_request.is_disconnected():
                    logger.info("Chat: client disconnected, setting stop_event")
                    stop_event.set()
                    return
                await asyncio.sleep(0.2)  # 检查频率 5Hz, 用户点停止 200ms 内生效

        async def generate():
            # 后台启动 disconnect watcher
            watcher_task = asyncio.create_task(disconnect_watcher())
            try:
                async for chunk in orchestrator.process_message_stream(
                    user_message=request.message,
                    scenario=request.scenario.value,
                    user_id=request.user_id,
                    conversation_id=request.conversation_id,
                    web_search_enabled=request.web_search_enabled,
                    deep_thinking_enabled=request.deep_thinking_enabled,
                    force_tier=effective_force_tier,
                    stop_event=stop_event,
                ):
                    # 额外保险: yield 之间也 check
                    if await fastapi_request.is_disconnected():
                        stop_event.set()
                        yield f"data: {json.dumps({'content': '[STOPPED]用户叫停了输出。'}, ensure_ascii=False)}\n\n"
                        return
                    yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                # 流结束
                if await fastapi_request.is_disconnected():
                    yield f"data: {json.dumps({'content': '[STOPPED]用户叫停了输出。'}, ensure_ascii=False)}\n\n"
                    return
            except asyncio.CancelledError:
                stop_event.set()
                yield f"data: {json.dumps({'content': '[STOPPED]用户叫停了输出。'}, ensure_ascii=False)}\n\n"
                raise
            finally:
                stop_event.set()
                watcher_task.cancel()
                try:
                    await watcher_task
                except (asyncio.CancelledError, Exception):
                    pass
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # 非流式
        result = await orchestrator.process_message(
            user_message=request.message,
            scenario=request.scenario.value,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            web_search_enabled=request.web_search_enabled,
            deep_thinking_enabled=request.deep_thinking_enabled,
            force_tier=effective_force_tier,
        )
        return result


# 取消 abort 端点 — 实际停止依赖 SSE 连接断开 (前端 AbortController 调 abort())
# 如果以后需要服务端主动取消, 再加这个端点
