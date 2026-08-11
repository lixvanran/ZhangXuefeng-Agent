"""TTS Service - MiniMax 语音合成
- 需要在 .env 配置 MINIMAX_API_KEY
- 没配的话 synthesize_speech() 返回 None, 上层用 503 友好提示
- 缓存: t2a_cache/<md5>.mp3 (按文本+voice+speed 缓存, 命中跳过 API)
"""
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

import aiofiles

from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = settings.BASE_DIR / "t2a_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def strip_markdown_for_tts(text: str) -> str:
    """去掉 markdown 格式, 让 TTS 念得自然"""
    if not text:
        return ""
    s = text
    # 代码块
    s = re.sub(r"```[\s\S]*?```", " ", s)
    # 行内代码
    s = re.sub(r"`[^`]+`", " ", s)
    # 表格
    s = re.sub(r"\|[^\n]*\|", " ", s)
    # 链接 [text](url) → text
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    # 标题
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    # 粗体/斜体/删除线
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s, flags=re.DOTALL)
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s, flags=re.DOTALL)
    s = re.sub(r"~~(.*?)~~", r"\1", s, flags=re.DOTALL)
    # 列表标记
    s = re.sub(r"^[\s]*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+\.\s+", "", s, flags=re.MULTILINE)
    # 引用
    s = re.sub(r"^>\s*", "", s, flags=re.MULTILINE)
    # 多余空白
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


async def synthesize_speech(
    text: str,
    voice_id: Optional[str] = None,
    speed: float = 1.0,
) -> Optional[bytes]:
    """TTS 合成, 返回 mp3 字节
    - 缓存: t2a_cache/<md5>.mp3
    - 默认 voice: settings.MINIMAX_VOICE_DEFAULT
    - 未配 MINIMAX_API_KEY → 返回 None
    """
    if not text:
        return None
    if not settings.MINIMAX_API_KEY:
        logger.warning("MINIMAX_API_KEY not set; TTS disabled")
        return None

    chosen_voice = voice_id or settings.ZHANG_VOICE_ID or settings.MINIMAX_VOICE_DEFAULT
    # 缓存 key — 包含 voice / speed / 文本
    cache_key = hashlib.md5(
        f"{chosen_voice}|{speed}|{text}".encode("utf-8")
    ).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 100:
        async with aiofiles.open(cache_path, "rb") as f:
            return await f.read()

    cleaned = strip_markdown_for_tts(text)[:2500]  # 限长度
    if not cleaned:
        return None

    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.MINIMAX_BASE_URL.rstrip('/')}/t2a_v2",
                headers={
                    "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.MINIMAX_TTS_MODEL,
                    "text": cleaned,
                    "voice_setting": {
                        "voice_id": chosen_voice,
                        "speed": speed,
                        "vol": 1.0,
                        "pitch": 0,
                    },
                    "audio_setting": {
                        "sample_rate": 32000,
                        "bitrate": 128000,
                        "format": "mp3",
                    },
                },
            )
        if resp.status_code != 200:
            logger.error(f"TTS failed: HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        audio_hex = (
            data.get("data", {}).get("audio")
            or data.get("audio")
            or ""
        )
        if not audio_hex:
            logger.error(f"TTS: no audio in response: {data}")
            return None
        # MiniMax 返回的是 hex 字符串 (不是 base64)
        audio_bytes = bytes.fromhex(audio_hex) if isinstance(audio_hex, str) else audio_hex
        async with aiofiles.open(cache_path, "wb") as f:
            await f.write(audio_bytes)
        return audio_bytes
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        return None


async def list_voices() -> list:
    """列可用 voice — 没配 key 时返回兜底预设"""
    if not settings.MINIMAX_API_KEY:
        return _default_voice_presets()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.MINIMAX_BASE_URL.rstrip('/')}/voice/list",
                headers={"Authorization": f"Bearer {settings.MINIMAX_API_KEY}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            voices = data.get("voice_list", data.get("voices", []))
            if voices:
                return voices
    except Exception as e:
        logger.error(f"list_voices failed: {e}")
    return _default_voice_presets()


def _default_voice_presets() -> list:
    return [
        {"voice_id": "male-qn-qingse", "voice_name": "清澈男声 (默认)"},
        {"voice_id": "male-qn-jingying", "voice_name": "精英男声 (成熟专业)"},
        {"voice_id": "female-shaonv", "voice_name": "少女音 (备用)"},
    ]
