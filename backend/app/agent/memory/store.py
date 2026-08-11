"""Memory Store - 底层 DB CRUD
所有函数接收 db session, 不持有 session (无状态, 易测)
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.db.database import MessageORM, ConversationORM, UserORM


SCENARIO_DEFAULT_TITLES = {
    "volunteer": "志愿咨询",
    "exam": "备考答疑",
    "chat": "随便聊聊",
}


def get_conversation(db: Session, conversation_id: int) -> Optional[ConversationORM]:
    return db.query(ConversationORM).filter_by(id=conversation_id).first()


def create_conversation(db: Session, user_id: int, scenario: str) -> ConversationORM:
    new_conv = ConversationORM(
        user_id=user_id,
        scenario=scenario,
        title=SCENARIO_DEFAULT_TITLES.get(scenario, "新对话"),
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv


def update_conversation_title(db: Session, conversation_id: int, new_title: str):
    conv = get_conversation(db, conversation_id)
    if conv:
        conv.title = new_title
        db.commit()


def list_conversation_messages(db: Session, conversation_id: int, limit: int = 10) -> List[MessageORM]:
    return (
        db.query(MessageORM)
        .filter_by(conversation_id=conversation_id)
        .order_by(MessageORM.created_at.desc())
        .limit(limit)
        .all()
    )[::-1]  # reverse to chronological order


def save_message(db: Session, conversation_id: int, role: str, content: str, tool_calls: str = None) -> MessageORM:
    msg = MessageORM(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
    )
    db.add(msg)
    db.commit()
    return msg


def get_user_by_id(db: Session, user_id: int) -> Optional[UserORM]:
    return db.query(UserORM).filter_by(id=user_id).first()


def get_user_profile(db: Session, user_id: int) -> Dict:
    """拉用户画像; 不存在时给个 default"""
    user = get_user_by_id(db, user_id)
    if not user:
        return {"name": "Student", "education_stage": "high"}
    return {
        "name": user.name,
        "education_stage": user.education_stage,
        "province": user.province,
        "score": user.score,
        "rank": user.rank,
        "target": user.target,
        "interests": user.interests,
        "background": user.background,
    }
