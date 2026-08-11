"""User Service - 用户/画像管理
"""
from typing import Dict, Optional
from app.db.database import SessionLocal, UserORM
from app.agent.memory import MemoryManager


def get_or_create_default_user(name: str = "小白", education_stage: str = "high") -> Dict:
    """获取默认用户(用于演示), 不存在就创建"""
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter_by(name=name).first()
        if not user:
            user = UserORM(name=name, education_stage=education_stage)
            db.add(user)
            db.commit()
            db.refresh(user)
        return _user_to_dict(user)
    finally:
        db.close()


def get_user(user_id: int) -> Optional[Dict]:
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter_by(id=user_id).first()
        return _user_to_dict(user) if user else None
    finally:
        db.close()


def update_user(user_id: int, updates: Dict) -> Optional[Dict]:
    """更新用户画像 (name / province / score / rank / target / interests / background / education_stage)"""
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter_by(id=user_id).first()
        if not user:
            return None
        for k, v in updates.items():
            if hasattr(user, k) and v is not None:
                setattr(user, k, v)
        db.commit()
        db.refresh(user)
        return _user_to_dict(user)
    finally:
        db.close()


def _user_to_dict(user: UserORM) -> Dict:
    return {
        "id": user.id,
        "name": user.name,
        "education_stage": user.education_stage,
        "province": user.province,
        "score": user.score,
        "rank": user.rank,
        "target": user.target,
        "interests": user.interests,
        "background": user.background,
    }
