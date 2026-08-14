"""Settings API - v0.9.1 新增
- GET/PUT 模型选择 (low/mid/high 档)
- GET API 状态 + OpenRouter 余额/消费
"""
import logging
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db, UserPreferenceORM
from app.core.config import settings
from app.agent.routing.model_whitelist import (
    MODEL_WHITELIST,
    DEFAULT_TIER_MODELS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["系统设置"])


# ===== Pydantic schemas =====

class ModelSelection(BaseModel):
    """用户对三档模型的选择"""
    low: str
    medium: str
    high: str


class ModelSettings(BaseModel):
    """完整的模型设置 (含每档可选列表)"""
    whitelist: dict  # { low: [...], medium: [...], high: [...] }
    defaults: dict   # { low: ..., medium: ..., high: ... }
    current: ModelSelection


class UsageResponse(BaseModel):
    """OpenRouter 余额/消费"""
    ok: bool
    email: Optional[str] = None
    is_free_tier: Optional[bool] = None
    limit: Optional[float] = None          # 总额度 ($)
    limit_remaining: Optional[float] = None  # 剩余额度 ($)
    usage: Optional[float] = None         # 已用 ($)
    error: Optional[str] = None


# ===== 工具函数 =====

def _get_pref(db: Session, user_id: int, key: str, default=None):
    """读一个用户偏好"""
    row = db.query(UserPreferenceORM).filter_by(user_id=user_id, key=key).first()
    if row and row.value is not None:
        return row.value
    return default


def _set_pref(db: Session, user_id: int, key: str, value):
    """写一个用户偏好 (upsert)"""
    row = db.query(UserPreferenceORM).filter_by(user_id=user_id, key=key).first()
    if row:
        row.value = value
    else:
        row = UserPreferenceORM(user_id=user_id, key=key, value=value)
        db.add(row)
    db.commit()
    return row


def _validate_model_in_whitelist(tier: str, model: str) -> None:
    """校验模型在白名单内, 不在就 raise"""
    if tier not in MODEL_WHITELIST:
        raise HTTPException(400, f"未知档位: {tier}")
    allowed = MODEL_WHITELIST[tier]
    if model not in allowed:
        raise HTTPException(
            400,
            f"模型 {model} 不在 {tier} 档白名单内. 允许: {', '.join(allowed)}"
        )


# ===== API 端点 =====

@router.get("/models", response_model=ModelSettings)
async def get_model_settings(user_id: int = 1, db: Session = Depends(get_db)):
    """获取模型设置: 白名单 + 默认 + 当前选择"""
    current = {
        "low": _get_pref(db, user_id, "model_low", DEFAULT_TIER_MODELS["low"]),
        "medium": _get_pref(db, user_id, "model_medium", DEFAULT_TIER_MODELS["medium"]),
        "high": _get_pref(db, user_id, "model_high", DEFAULT_TIER_MODELS["high"]),
    }
    return ModelSettings(
        whitelist=MODEL_WHITELIST,
        defaults=DEFAULT_TIER_MODELS,
        current=ModelSelection(**current),
    )


@router.put("/models")
async def update_model_settings(
    selection: ModelSelection,
    user_id: int = 1,
    db: Session = Depends(get_db),
):
    """更新用户的三档模型选择

    每个模型必须在该档的白名单内, 否则 400
    """
    # 校验
    for tier, model in [
        ("low", selection.low),
        ("medium", selection.medium),
        ("high", selection.high),
    ]:
        _validate_model_in_whitelist(tier, model)

    # 写入
    _set_pref(db, user_id, "model_low", selection.low)
    _set_pref(db, user_id, "model_medium", selection.medium)
    _set_pref(db, user_id, "model_high", selection.high)

    logger.info(
        f"User {user_id} updated models: low={selection.low}, "
        f"medium={selection.medium}, high={selection.high}"
    )
    return {
        "success": True,
        "message": "模型设置已更新, 下次对话生效",
        "current": selection.dict(),
    }


@router.get("/usage", response_model=UsageResponse)
async def get_usage():
    """查询 OpenRouter 余额/消费

    调 https://openrouter.ai/api/v1/auth/key (不消耗 token)
    返回: email, is_free_tier, limit, limit_remaining, usage
    """
    if not settings.LLM_API_KEY:
        return UsageResponse(ok=False, error="LLM_API_KEY 未设置, 无法查询余额")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            )
        if r.status_code == 200:
            data = r.json().get("data", {})
            return UsageResponse(
                ok=True,
                email=data.get("email"),
                is_free_tier=data.get("is_free_tier"),
                limit=data.get("limit"),
                limit_remaining=data.get("limit_remaining"),
                usage=data.get("usage"),
            )
        elif r.status_code == 401:
            return UsageResponse(ok=False, error="key 无效 (401), 请检查 .env 的 LLM_API_KEY")
        else:
            return UsageResponse(ok=False, error=f"OpenRouter 返回 {r.status_code}: {r.text[:200]}")
    except httpx.ConnectError as e:
        return UsageResponse(ok=False, error=f"连不上 OpenRouter: {e}")
    except Exception as e:
        logger.error(f"Usage query error: {e}")
        return UsageResponse(ok=False, error=str(e))


@router.get("/status")
async def get_status(db: Session = Depends(get_db)):
    """简化的系统状态 (前端系统设置页用)

    返回: key 是否设置, 基础 URL, 当前模型选择
    """
    return {
        "llm_api_key_set": bool(settings.LLM_API_KEY),
        "llm_api_key_prefix": (settings.LLM_API_KEY[:12] + "...") if settings.LLM_API_KEY else None,
        "llm_base_url": settings.LLM_BASE_URL,
        "embedding_provider": getattr(settings, "embedding_provider", "unknown"),
        "tts_enabled": bool(settings.MINIMAX_API_KEY),
        "current_models": {
            "low": _get_pref(db, 1, "model_low", DEFAULT_TIER_MODELS["low"]),
            "medium": _get_pref(db, 1, "model_medium", DEFAULT_TIER_MODELS["medium"]),
            "high": _get_pref(db, 1, "model_high", DEFAULT_TIER_MODELS["high"]),
        },
    }
