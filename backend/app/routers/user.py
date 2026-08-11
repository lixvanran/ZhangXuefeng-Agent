"""User API - all fields optional except name"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db, UserORM

router = APIRouter(prefix="/api/user", tags=["用户"])


@router.get("/profile")
async def get_profile(user_id: int = 1, db: Session = Depends(get_db)):
    user = db.query(UserORM).filter_by(id=user_id).first()
    if not user:
        # Auto-create default user
        user = UserORM(id=user_id, name="Student", education_stage="high")
        db.add(user)
        db.commit()
        db.refresh(user)
    return {
        "id": user.id,
        "name": user.name,
        "education_stage": user.education_stage or "high",
        "province": user.province,
        "score": user.score,
        "rank": user.rank,
        "target": user.target,
        "interests": user.interests,
        "background": user.background,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


@router.put("/profile")
async def update_profile(
    name: str = None,
    education_stage: str = None,
    province: str = None,
    score: int = None,
    rank: int = None,
    target: str = None,
    interests: str = None,
    background: str = None,
    user_id: int = 1,
    db: Session = Depends(get_db),
):
    """Update user profile. ALL fields optional."""
    user = db.query(UserORM).filter_by(id=user_id).first()
    if not user:
        user = UserORM(id=user_id, name=name or "Student")
        db.add(user)
        db.flush()

    # Only update fields that were explicitly provided
    if name is not None:
        user.name = name
    if education_stage is not None:
        user.education_stage = education_stage
    if province is not None:
        user.province = province or None
    if score is not None:
        user.score = score
    if rank is not None:
        user.rank = rank
    if target is not None:
        user.target = target or None
    if interests is not None:
        user.interests = interests or None
    if background is not None:
        user.background = background or None

    db.commit()
    db.refresh(user)
    return {
        "message": "Updated",
        "profile": {
            "name": user.name,
            "education_stage": user.education_stage,
            "province": user.province,
            "score": user.score,
            "rank": user.rank,
            "target": user.target,
            "interests": user.interests,
            "background": user.background,
        }
    }


@router.get("/education-stages")
async def list_education_stages():
    """Available education stages"""
    return {
        "stages": [
            {"value": "primary", "label": "小学", "icon": "🎒"},
            {"value": "middle", "label": "初中", "icon": "📚"},
            {"value": "high", "label": "高中", "icon": "🎓"},
            {"value": "vocational", "label": "职高/中专", "icon": "🔧"},
            {"value": "junior_college", "label": "大专", "icon": "🏫"},
            {"value": "bachelor", "label": "本科", "icon": "🎯"},
            {"value": "master", "label": "考研/硕士", "icon": "📖"},
            {"value": "abroad", "label": "留学", "icon": "✈️"},
            {"value": "working", "label": "在职/工作", "icon": "💼"},
            {"value": "other", "label": "其他", "icon": "✨"},
        ]
    }
