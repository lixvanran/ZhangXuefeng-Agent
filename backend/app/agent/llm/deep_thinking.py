"""深度思考客户端 - 调用支持 reasoning_content 的模型
（如 DeepSeek R1、GLM-Z1、Claude with thinking）
流式输出 (event, content) 元组：
  - ("reasoning", text)   思考过程增量
  - ("content", text)     最终回答增量
  - ("tool_call_delta", tc) 工具调用增量
  - ("done", None)        流结束
  - ("error", msg)        错误
"""
import logging
from typing import AsyncGenerator, Optional

from app.agent.llm.base import BaseLLMClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class DeepThinkingClient(BaseLLMClient):
    """深度思考专用 - 暴露 reasoning_content"""

    def __init__(self):
        super().__init__(
            base_url=settings.DEEP_THINKING_BASE_URL or settings.LLM_BASE_URL,
            api_key=settings.DEEP_THINKING_API_KEY or settings.LLM_API_KEY,
        )
        self.model = settings.DEEP_THINKING_MODEL
        self.fallback_models = self._parse_model_list(
            settings.DEEP_THINKING_FALLBACK_MODELS, exclude=self.model
        )
        self.effort = settings.DEEP_THINKING_EFFORT
        self.temperature = 0.5  # 深度思考用低温度保稳定

    def _build_kwargs(self, model: str, messages, tools: Optional[list], stream: bool) -> dict:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        # reasoning_effort 只用在原生支持该参数的 provider (如 DeepSeek 直连)
        # OpenRouter 走 extra_body, 其他 provider 不传 (避免 400)
        if "deepseek" in model.lower() and not self.is_openrouter:
            kwargs["reasoning_effort"] = self.effort
        elif self.is_openrouter:
            # OpenRouter 统一用 extra_body 包 reasoning
            kwargs["extra_body"] = {"reasoning": {"effort": self.effort}}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    async def chat(self, messages, tools: Optional[list] = None):
        """非流式"""
        last_err = None
        for m in [self.model] + self.fallback_models:
            try:
                return await self._do_chat(m, messages, tools)
            except Exception as e:
                logger.warning(f"DeepThinking {m} failed: {e}")
                last_err = e
        return {
            "content": f"（深度思考模型不可用，已用主模型）{last_err or Exception('all failed')}",
            "reasoning": "",
            "tool_calls": None,
            "finish_reason": "error",
        }

    async def stream_chat(self, messages, tools: Optional[list] = None, stop_event: Optional["asyncio.Event"] = None) -> AsyncGenerator[tuple, None]:
        """流式 - yield (event_type, data)
        v0.8.0+: stop_event - 用户按 Stop 按钮会 set, 每个 chunk 之前 check
        """
        import asyncio as _asyncio
        tried = set()
        last_err = None
        for m in [self.model] + self.fallback_models:
            if m in tried:
                continue
            tried.add(m)
            try:
                async for ev in self._do_stream(m, messages, tools, stop_event=stop_event):
                    yield ev
                return
            except Exception as e:
                logger.warning(f"DeepThinking stream {m} failed: {e}")
                last_err = e
                continue
        yield ("error", f"所有深度思考模型都不可用: {last_err}")

    async def _do_chat(self, model: str, messages, tools: Optional[list]):
        kwargs = self._build_kwargs(model, messages, tools, stream=False)
        response = await self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        reasoning = self._extract_reasoning(msg)
        return {
            "content": msg.content or "",
            "reasoning": reasoning,
            "tool_calls": msg.tool_calls,
            "finish_reason": response.choices[0].finish_reason,
        }

    async def _do_stream(self, model: str, messages, tools: Optional[list], stop_event=None) -> AsyncGenerator[tuple, None]:
        kwargs = self._build_kwargs(model, messages, tools, stream=True)
        stream = await self.client.chat.completions.create(**kwargs)
        async for chunk in stream:
            # v0.8.0: 每个 chunk 之前 check stop_event
            if stop_event is not None and stop_event.is_set():
                yield ("stopped", "用户中途叫停 (deep thinking 流中)")
                return
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            rc = self._extract_reasoning(delta)
            if rc:
                yield ("reasoning", rc)
            if delta.content:
                yield ("content", delta.content)
            if getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    yield ("tool_call_delta", tc)
        yield ("done", None)

    @staticmethod
    def _extract_reasoning(msg) -> str:
        """从 message/delta 提取 reasoning - 兼容多种字段名"""
        rc = getattr(msg, "reasoning_content", None)
        if not rc:
            rc = getattr(msg, "reasoning", None)
        if not rc and hasattr(msg, "model_dump"):
            dumped = msg.model_dump()
            rc = dumped.get("reasoning_content") or dumped.get("reasoning")
        return rc or ""


deep_thinking_client = DeepThinkingClient()
