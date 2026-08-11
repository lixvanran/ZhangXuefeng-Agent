"""TTS Router: AI voice output (Zhang Xuefeng style).

v0.7.9.4+: Use MiniMax TTS (with optional voice cloning).
- Default voice: MINIMAX_VOICE_DEFAULT (默认 male-qn-qingse)
- If ZHANG_VOICE_ID is set in .env (after a successful clone_voice),
  use that cloned voice instead.

Workflow for cloning Zhang's voice:
1. Drop a 30s-2min audio sample at samples/zhangxuefeng.mp3
2. Run `python scripts/clone_zhang_voice.py`
3. .env gets updated with ZHANG_VOICE_ID automatically
4. Restart backend; TTS now uses the cloned voice

If no sample or no MINIMAX_API_KEY, TTS endpoint returns 503 with
a clear instruction (chat is unaffected).
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.tts_service import synthesize_speech, list_voices

logger = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice_id: str | None = Field(None, description="Override voice id (default: ZHANG_VOICE_ID or MINIMAX_VOICE_DEFAULT)")
    speed: float = Field(1.0, ge=0.5, le=2.0)
    emotion: str = Field("neutral")


def _tts_unavailable_detail() -> dict:
    return {
        "code": "TTS_NOT_CONFIGURED",
        "message": "TTS 未启用：在 backend/.env 配置 MINIMAX_API_KEY 后重启即可。",
        "docs": "https://platform.MiniMax.io",
    }


@router.post("/api/tts")
async def text_to_speech(req: TTSRequest) -> Response:
    """Synthesize text to speech using MiniMax TTS.
    Returns audio/mpeg (mp3) bytes.
    Returns 503 if TTS not configured.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    if not settings.MINIMAX_API_KEY:
        raise HTTPException(status_code=503, detail=_tts_unavailable_detail())

    voice_id = req.voice_id or settings.ZHANG_VOICE_ID or settings.MINIMAX_VOICE_DEFAULT

    try:
        audio = await synthesize_speech(req.text, voice_id=voice_id, speed=req.speed)
    except Exception as e:
        logger.exception("TTS error")
        raise HTTPException(status_code=500, detail=f"TTS internal error: {e}")

    if audio is None:
        raise HTTPException(status_code=502, detail="TTS service returned no audio")

    return Response(content=audio, media_type="audio/mpeg")


@router.get("/api/tts/voices")
async def get_voices_endpoint() -> dict:
    """List available voices. Returns the active voice id and a few presets."""
    voices = await list_voices()
    return {
        "active_voice_id": settings.ZHANG_VOICE_ID or settings.MINIMAX_VOICE_DEFAULT,
        "is_cloned": bool(settings.ZHANG_VOICE_ID),
        "tts_enabled": bool(settings.MINIMAX_API_KEY),
        "voices": voices,
    }
