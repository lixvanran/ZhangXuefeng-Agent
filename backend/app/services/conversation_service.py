"""Conversation Service - 会话管理
封装 memory 的常用操作
"""
from typing import List, Dict, Optional
from app.db.database import SessionLocal
from app.agent.memory import MemoryManager


def get_memory() -> MemoryManager:
    return MemoryManager()


def list_user_conversations(user_id: int) -> List[Dict]:
    """列出用户的所有会话
    Returns: [{id, title, scenario, created_at, updated_at, message_count}, ...]
    """
    from app.db.database import ConversationORM, MessageORM
    db = SessionLocal()
    try:
        convs = db.query(ConversationORM).filter_by(user_id=user_id).order_by(ConversationORM.created_at.desc()).all()
        result = []
        for c in convs:
            count = db.query(MessageORM).filter_by(conversation_id=c.id).count()
            result.append({
                "id": c.id,
                "title": c.title,
                "scenario": c.scenario,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if hasattr(c, "updated_at") and c.updated_at else None,
                "message_count": count,
            })
        return result
    finally:
        db.close()


def get_conversation_messages(conversation_id: int, limit: int = 100) -> List[Dict]:
    """拉一个会话的全部消息"""
    from app.db.database import MessageORM
    db = SessionLocal()
    try:
        msgs = db.query(MessageORM).filter_by(conversation_id=conversation_id).order_by(MessageORM.created_at.asc()).all()
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ]
    finally:
        db.close()


def delete_conversation(conversation_id: int) -> bool:
    """删除一个会话 (含消息)"""
    from app.db.database import MessageORM, ConversationORM
    db = SessionLocal()
    try:
        db.query(MessageORM).filter_by(conversation_id=conversation_id).delete()
        deleted = db.query(ConversationORM).filter_by(id=conversation_id).delete()
        db.commit()
        return deleted > 0
    finally:
        db.close()


def delete_all_user_conversations(user_id: int) -> int:
    """删一个用户的所有会话"""
    from app.db.database import MessageORM, ConversationORM
    db = SessionLocal()
    try:
        conv_ids = [c.id for c in db.query(ConversationORM).filter_by(user_id=user_id).all()]
        if not conv_ids:
            return 0
        db.query(MessageORM).filter(MessageORM.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        n = db.query(ConversationORM).filter_by(user_id=user_id).delete()
        db.commit()
        return n
    finally:
        db.close()
