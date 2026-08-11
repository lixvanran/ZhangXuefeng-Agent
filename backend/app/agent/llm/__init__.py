"""LLM 客户端模块 - v0.7.5 模块化重构
- base.py: 共享基类（client init, fallback logic, error handling）
- openrouter.py: 通用 LLM 客户端（兼容 OpenAI SDK）
- deep_thinking.py: 深度思考专用（reasoning_content 流式）
- vision.py: 看图专用（base64 → 文字描述）
"""
from app.agent.llm.base import BaseLLMClient
from app.agent.llm.openrouter import LLMClient, llm_client
from app.agent.llm.deep_thinking import DeepThinkingClient, deep_thinking_client
from app.agent.llm.vision import VisionClient, vision_client

__all__ = [
    "BaseLLMClient",
    "LLMClient",
    "llm_client",
    "DeepThinkingClient",
    "deep_thinking_client",
    "VisionClient",
    "vision_client",
]
