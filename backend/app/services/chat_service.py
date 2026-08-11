"""Chat Service - 聊天业务编排
router → chat_service → orchestrator
"""
import json
import logging
from typing import AsyncGenerator, Dict, Optional

from app.agent.orchestrator import orchestrator

logger = logging.getLogger(__name__)


async def process_chat(
    user_message: str,
    scenario: str = "chat",
    user_id: int = 1,
    conversation_id: Optional[int] = None,
    web_search_enabled: Optional[bool] = None,
    deep_thinking_enabled: Optional[bool] = None,
) -> Dict:
    """非流式聊天 - 一次返回完整结果"""
    return await orchestrator.process_message(
        user_message=user_message,
        scenario=scenario,
        user_id=user_id,
        conversation_id=conversation_id,
        web_search_enabled=web_search_enabled,
        deep_thinking_enabled=deep_thinking_enabled,
    )


async def process_chat_stream(
    user_message: str,
    scenario: str = "chat",
    user_id: int = 1,
    conversation_id: Optional[int] = None,
    web_search_enabled: Optional[bool] = None,
    deep_thinking_enabled: Optional[bool] = None,
) -> AsyncGenerator[str, None]:
    """流式聊天 - SSE 增量输出"""
    async for chunk in orchestrator.process_message_stream(
        user_message=user_message,
        scenario=scenario,
        user_id=user_id,
        conversation_id=conversation_id,
        web_search_enabled=web_search_enabled,
        deep_thinking_enabled=deep_thinking_enabled,
    ):
        yield chunk
