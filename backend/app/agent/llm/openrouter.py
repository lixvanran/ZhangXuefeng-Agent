"""通用 LLM 客户端 - 通过 OpenRouter 一把 Key 调 6 模型
带 fallback 链，model 挂了自动切下一个
"""
import logging
from typing import AsyncGenerator, Optional

from app.agent.llm.base import BaseLLMClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClient(BaseLLMClient):
    """通用聊天客户端，支持多模型 fallback 链"""

    def __init__(self):
        super().__init__()
        self.model = settings.LLM_MODEL
        self.fallback_models = self._parse_model_list(
            settings.LLM_FALLBACK_MODELS, exclude=self.model
        )

    async def chat(self, messages, tools: Optional[list] = None):
        """非流式调用 + fallback"""
        try:
            return await self._do_chat(self.model, messages, tools)
        except Exception as e:
            logger.warning(f"Primary {self.model} failed: {e}")
        for fb in self.fallback_models:
            try:
                logger.info(f"Trying fallback: {fb}")
                return await self._do_chat(fb, messages, tools)
            except Exception as e:
                logger.warning(f"Fallback {fb} failed: {e}")
        return {
            "content": self._fallback_response(Exception("All models failed")),
            "tool_calls": None,
            "finish_reason": "error",
        }

    async def stream_chat(self, messages, tools: Optional[list] = None, stop_event=None) -> AsyncGenerator[str, None]:
        """流式调用 + fallback
        v0.8.0+: stop_event 支持中途打断
        """
        tried = set()
        for model in [self.model] + self.fallback_models:
            if model in tried:
                continue
            tried.add(model)
            try:
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "stream": True,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                stream = await self.client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    # v0.8.0: 每个 chunk 之前 check stop_event
                    if stop_event is not None and stop_event.is_set():
                        return
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    # v0.8.0 修复: 某些模型 (GLM 5.x, minimax) 默认带 reasoning
                    # 如果 content 为空但 reasoning 有东西, 把 reasoning 也 yield 出去
                    # 用一个特殊前缀 [💭] 标记 reasoning 块, 前端可以选择是否隐藏
                    if delta.content:
                        yield delta.content
                    elif hasattr(delta, "reasoning") and delta.reasoning:
                        yield f"[💭 {delta.reasoning}]"
                    elif hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        yield f"[💭 {delta.reasoning_content}]"
                return
            except Exception as e:
                logger.warning(f"Stream {model} failed: {e}")
                continue
        yield self._fallback_response(Exception("All stream models failed"))

    async def _do_chat(self, model: str, messages, tools: Optional[list]):
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        content = msg.content
        # v0.8.0 修复: GLM 5.x / minimax 等默认带 reasoning, 有时 content 是 None
        # 如果 content 是 None 但 reasoning 有东西, 提示 max_tokens 不够
        if not content:
            reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
            if reasoning:
                content = f"[模型在 reasoning 阶段用了 {len(reasoning)} 字符, 但 max_tokens={self.max_tokens} 不够出最终答案。请提高 max_tokens 重试, 或换非 reasoning 模型。]"
            else:
                content = "[模型未返回内容]"
        return {
            "content": content,
            "tool_calls": msg.tool_calls,
            "finish_reason": response.choices[0].finish_reason,
        }

    async def embedding(self, text: str) -> list[float]:
        """调 OpenAI-compatible embedding 接口
        v0.9.8: 共用 LLM_API_KEY (OpenRouter 支持 openai/text-embedding-3-small)
        - 走 LLM_BASE_URL (即 OpenRouter) + LLM_API_KEY
        - 失败时返回零向量 (RAG 会自然降级)
        """
        if not settings.LLM_API_KEY:
            logger.warning("LLM_API_KEY not set; embedding returns zero vector")
            return [0.0] * 1024
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
            )
            response = await client.embeddings.create(
                model="openai/text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return [0.0] * 1024


# 模块级单例
llm_client = LLMClient()
