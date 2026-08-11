"""视觉客户端 - 把图片转成文字描述
不直接调用昂贵的多模态模型看图，先用便宜的 vision model 转文字，
再把描述喂给主模型回答，省成本也兼容 deepseek-v4-pro 这类不支持 vision 的模型
"""
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple

from app.agent.llm.base import BaseLLMClient
from app.core.config import settings

logger = logging.getLogger(__name__)

MIME_MAP = {
    "jpg": "jpeg", "jpeg": "jpeg", "png": "png",
    "gif": "gif", "webp": "webp",
}

DEFAULT_PROMPT = (
    "请详细描述这张图片。如果是题目（含数学公式、几何图、错题照片等），"
    "请逐字转录题目原文、所有公式、图形中的标注；如果看不清就说'看不清'；"
    "如果图里有错误标记、解题痕迹、同伴注解也要讲出来。"
)


class VisionClient(BaseLLMClient):
    """看图转文字 - 给主模型当'眼睛'"""

    def __init__(self):
        super().__init__(
            base_url=settings.VISION_BASE_URL or settings.LLM_BASE_URL,
            api_key=settings.VISION_API_KEY or settings.LLM_API_KEY,
        )
        self.model = settings.VISION_MODEL
        self.fallback_models = self._parse_model_list(
            settings.VISION_FALLBACK_MODELS, exclude=self.model
        )
        self.temperature = 0.2  # 看图要稳定

    async def describe(self, image_path: str, prompt: Optional[str] = None) -> Tuple[bool, str, str]:
        """读图, 返回 (ok, description, model_used)
        - ok=True: 成功, description 是图片文字描述
        - ok=False: 全部失败, description 是错误原因 (不含 '[Visión失败]' 前缀让上层识别)
        v0.8.0: 改为返回 tuple, 明确告知上层成功/失败
        """
        p = Path(image_path)
        if not p.exists() or not p.is_file():
            return False, f"图片文件不存在: {p}", "none"
        mime = MIME_MAP.get(p.suffix.lower().lstrip("."), "jpeg")
        try:
            data = base64.b64encode(p.read_bytes()).decode("ascii")
            data_url = f"data:image/{mime};base64,{data}"
        except Exception as e:
            logger.error(f"Vision: failed to read image {p}: {e}")
            return False, f"读图失败: {e}", "none"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or DEFAULT_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]

        for m in [self.model] + self.fallback_models:
            try:
                resp = await self.client.chat.completions.create(
                    model=m,
                    messages=messages,
                    max_tokens=1000,
                    temperature=self.temperature,
                )
                text = resp.choices[0].message.content or ""
                if text.strip():
                    logger.info(f"Vision {m} described {p.name} ({len(text)} chars)")
                    return True, text.strip(), m
            except Exception as e:
                logger.warning(f"Vision {m} failed: {e}")
                continue
        return False, f"所有 vision 模型都不可用 (试了 {len(self.fallback_models)+1} 个: {self.model} + {self.fallback_models})", "none"


vision_client = VisionClient()
