"""TTS Service — v0.9.8 stub
旧版本调 MiniMax TTS API, v0.9.8 起改用浏览器 Web Speech API (前端处理)
保留这个文件是为了向后兼容可能的旧 import 路径
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def strip_markdown_for_tts(text: str) -> str:
    """去掉 markdown 格式, 让 TTS 念得自然 (前后端共用)"""
    if not text:
        return ""
    s = text
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`[^`]+`", " ", s)
    s = re.sub(r"\|[^\n]*\|", " ", s)
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s, flags=re.DOTALL)
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s, flags=re.DOTALL)
    s = re.sub(r"~~(.*?)~~", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"^[\s]*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+\.\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^>\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


async def synthesize_speech(
    text: str,
    voice_id: Optional[str] = None,
    speed: float = 1.0,
) -> Optional[bytes]:
    """v0.9.8 stub: TTS 改用浏览器 Web Speech API, 后端不再合成音频
    返回 None — 前端已用 window.speechSynthesis.speak() 直接读
    """
    logger.debug(f"TTS stub called: {len(text)} chars, voice={voice_id}, speed={speed}")
    return None


async def list_voices() -> list:
    """v0.9.8 stub: 返回浏览器内置 voice 预设 (前端展示用)"""
    return [
        {"voice_id": "browser-zh-male", "voice_name": "浏览器中文男声 (默认)"},
        {"voice_id": "browser-zh-female", "voice_name": "浏览器中文女声"},
        {"voice_id": "browser-en-male", "voice_name": "Browser English Male"},
    ]


def _default_voice_presets() -> list:
    return list_voices().__class__  # 占位, 不再使用
