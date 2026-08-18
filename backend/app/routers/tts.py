"""TTS Router: v0.9.8 起改用浏览器 Web Speech API (前端), 后端 stub

v0.9.8 简化:
- 不再依赖 MINIMAX_API_KEY
- 浏览器原生 speechSynthesis.speak(), 0 key 0 成本
- 保留 /api/tts 和 /api/tts/voices 接口兼容性, 但返回 web speech fallback 提示
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice_id: str | None = None
    speed: float = Field(1.0, ge=0.5, le=2.0)
    emotion: str = "neutral"


@router.post("/api/tts")
async def text_to_speech(req: TTSRequest) -> dict:
    """v0.9.8: TTS 由前端浏览器 Web Speech 接管
    后端不再合成音频. 老客户端可继续调, 收到 200 + use_browser_tts 提示后 fallback.
    """
    return {
        "use_browser_tts": True,
        "text": req.text,
        "rate": req.speed,
        "lang": "zh-CN",
        "message": "v0.9.8+: 浏览器原生 Web Speech API, 0 key 0 成本",
    }


@router.get("/api/tts/voices")
async def get_voices_endpoint() -> dict:
    """v0.9.8: 返回浏览器内置 voice 预设 (前端可继续展示)
    实际 voice 由 window.speechSynthesis.getVoices() 提供.
    """
    return {
        "active_voice_id": "browser-zh-male",
        "is_cloned": False,
        "tts_enabled": True,  # 浏览器都支持
        "tts_engine": "browser_web_speech_api",
        "voices": [
            {"voice_id": "browser-zh-male", "voice_name": "浏览器中文男声 (默认)"},
            {"voice_id": "browser-zh-female", "voice_name": "浏览器中文女声"},
            {"voice_id": "browser-en-male", "voice_name": "Browser English Male"},
        ],
        "note": "v0.9.8+: 实际音色取决于操作系统/浏览器内置 voice, 0 key 0 成本",
    }
