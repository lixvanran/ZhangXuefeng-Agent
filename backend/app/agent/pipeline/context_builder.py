"""上下文构建器 - 拼 LLM 要用的 messages
- RAG 检索 (user resources + KB)
- 历史消息 (memory)
- system prompt (scenario + profile + RAG context)
- user content (含可选图片)
"""
import logging
from typing import Dict, List, Optional

from app.core.config import settings
from app.agent.rag import rag_engine
from app.agent.prompts import build_system_prompt
from app.agent.memory.manager import MemoryManager
from app.agent.pipeline.preprocessor import build_user_content

logger = logging.getLogger(__name__)


def _resolve_toggle(caller_value, settings_attr: str) -> bool:
    if caller_value is not None:
        return caller_value
    return getattr(settings, settings_attr, False)


def _summarize_rag(user_resources: list, kb_results: list) -> Dict:
    """生成 RAG 用量摘要 (返回给前端)"""
    return {
        "user_resources": [
            {
                "code": r["metadata"].get("code", ""),
                "title": r["metadata"].get("title", ""),
                "type": r["metadata"].get("type", "material"),
                "score": r.get("score", 0),
                "has_file": bool(r["metadata"].get("file_path")),
            }
            for r in user_resources
        ],
        "kb_results": [
            {"title": r["title"], "type": r["type"], "score": r.get("score", 0)}
            for r in kb_results
        ],
    }


async def build_messages(
    user_message: str,
    scenario: str,
    user_id: int,
    memory: MemoryManager,
    conversation_id: Optional[int] = None,
    web_search_enabled: Optional[bool] = None,
    deep_thinking_enabled: Optional[bool] = None,
    include_image: bool = False,
) -> Dict:
    """拼装完整 messages + RAG 摘要
    Returns: {
        "messages": [...],
        "rag_summary": {...},
        "user_resources": [...],
        "kb_results": [...],
    }
    """
    # 1) 拉历史 + profile
    history = memory.get_conversation_history(conversation_id, limit=10) if conversation_id else []
    user_profile = memory.get_user_profile(user_id)

    # 2) RAG
    user_resources = rag_engine.search_user_resources(user_message, user_id, top_k=3)
    kb_results = rag_engine.search_knowledge_base(user_message, top_k=5)
    rag_context = rag_engine.build_context(user_resources, kb_results)
    rag_summary = _summarize_rag(user_resources, kb_results)

    # 3) 解析 toggle
    ws_on = _resolve_toggle(web_search_enabled, "WEB_SEARCH_ENABLED")
    dt_on = _resolve_toggle(deep_thinking_enabled, "DEEP_THINKING_ENABLED")

    # 4) System prompt
    system_prompt = build_system_prompt(
        scenario, user_profile, rag_context,
        web_search_enabled=ws_on, deep_thinking_enabled=dt_on,
    )

    # 5) 拼 messages
    messages: List[Dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    # 6) user content (含图片或图片描述)
    # v0.8.0: 默认 include_image=False, 统一用 vision_client 转文字
    #   因为中档/高档 primary (GLM 5.2, Grok 4.20) 都不支持 vision
    #   (实测 OpenRouter 上 z-ai/glm-5.2, x-ai/grok-4.20-multi-agent 返回 404 image)
    #   只有 minimax/minimax-m3 (low 档) 支持多模态
    #   统一走文字描述, 确保全档位都能处理带图消息
    top_resource = user_resources[0] if user_resources else None
    user_content = await build_user_content(
        user_message, top_resource, include_image=include_image,
    )
    messages.append(user_content)

    return {
        "messages": messages,
        "rag_summary": rag_summary,
        "user_resources": user_resources,
        "kb_results": kb_results,
        "ws_on": ws_on,
        "dt_on": dt_on,
    }
