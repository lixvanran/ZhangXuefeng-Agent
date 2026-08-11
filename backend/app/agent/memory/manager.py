"""Memory Manager - 业务封装层
组合 store 的底层 CRUD, 提供给 orchestrator 用
"""
import logging
from typing import List, Dict, Optional

from app.db.database import SessionLocal
from app.agent.memory.store import (
    get_conversation, create_conversation, update_conversation_title,
    list_conversation_messages, save_message,
    get_user_profile as _get_user_profile,
)

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, db_session=None):
        self.db = db_session or SessionLocal()

    def get_or_create_conversation(self, user_id: int, scenario: str, conversation_id: int = None) -> int:
        if conversation_id:
            existing = get_conversation(self.db, conversation_id)
            if existing:
                return existing.id
        new_conv = create_conversation(self.db, user_id, scenario)
        return new_conv.id

    def maybe_update_title(self, conversation_id: int, first_message: str):
        """Auto-generate title from first user message (only if still default)"""
        from app.agent.memory.store import SCENARIO_DEFAULT_TITLES
        conv = get_conversation(self.db, conversation_id)
        if not conv:
            return
        default_titles = set(SCENARIO_DEFAULT_TITLES.values()) | {"新对话"}
        if conv.title in default_titles:
            title = first_message.strip()[:30]
            if len(first_message) > 30:
                title += "..."
            update_conversation_title(self.db, conversation_id, title)

    def get_conversation_history(self, conversation_id: Optional[int], limit: int = 20) -> List[Dict]:
        """取某对话的历史消息 (按 conversation_id 严格隔离)
        v0.8.0: 默认 limit=20, 让长对话也有上下文
        - 不同 conversation_id 永远不会混消息
        - 没传 conversation_id 返回空 (新对话)
        """
        if not conversation_id:
            return []
        messages = list_conversation_messages(self.db, conversation_id, limit=limit)
        return [{"role": m.role, "content": m.content} for m in messages]

    def save_message(self, conversation_id: int, role: str, content: str, tool_calls: str = None):
        save_message(self.db, conversation_id, role, content, tool_calls)

    def get_user_profile(self, user_id: int) -> Dict:
        return _get_user_profile(self.db, user_id)

    def close(self):
        self.db.close()
