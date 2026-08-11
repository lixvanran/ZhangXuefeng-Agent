"""预处理器 - 消息预处理
- 描述上传图片 (vision_client.describe)
- 构造 user message content (含图片 / 文字描述)
"""
import base64
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.core.config import settings
from app.agent.llm.vision import vision_client

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MIME_MAP = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp"}
MAX_INLINE_IMAGE_SIZE = 4 * 1024 * 1024  # 4 MB


def _resolve_local_path(file_path: str) -> Optional[Path]:
    """把 /uploads/foo.png → backend/data/uploads/foo.png"""
    if file_path.startswith("/uploads/"):
        return settings.UPLOAD_DIR / file_path.replace("/uploads/", "", 1)
    return Path(file_path)


async def describe_top_image(top_resource: Optional[dict]) -> Tuple[bool, str, str]:
    """用 vision_client 描述 top resource 的图片
    Returns: (ok, description_or_error, model_used)
    v0.8.0: 透传 vision_client 返回的 (ok, desc, model) 三元组
    """
    if not top_resource:
        return False, "无附件", "none"
    meta = top_resource.get("metadata", {})
    file_path = meta.get("file_path", "")
    if not file_path:
        return False, "附件无文件路径", "none"
    local = _resolve_local_path(file_path)
    if not local.exists() or local.suffix.lower() not in IMAGE_SUFFIXES:
        return False, f"图片文件不存在或不是图片格式: {local}", "none"
    try:
        return await vision_client.describe(str(local))
    except Exception as e:
        logger.warning(f"vision describe failed: {e}")
        return False, f"读图异常: {e}", "none"


async def build_user_content(
    user_message: str,
    top_resource: Optional[dict] = None,
    include_image: bool = True,
    image_description: str = "",
    for_deep_thinking: bool = False,
) -> Dict:
    """构造 user message content
    - 包含图片:  (multimodal 直接看图, 限 < 4MB)
    - 描述:  (vision_client 先转文字再传, 给不支持 vision 的模型)
    - 无附件: 普通文本
    Args:
        for_deep_thinking: v0.8.0 — True 时强制走 Path B (文字描述) 而不送 inline 图。
          因为 deep_thinking 模型链 (DeepSeek R1 / Qwen) 全部不支持 vision,
          送 inline 图会 404 整个 deep_thinking 链路都挂。
    """
    if not top_resource:
        return {"role": "user", "content": user_message}

    meta = top_resource.get("metadata", {})
    file_path = meta.get("file_path", "")
    code = meta.get("code", "")
    title = meta.get("title", "")

    if not file_path:
        return {"role": "user", "content": user_message}

    local = _resolve_local_path(file_path)
    if not local.exists() or not local.is_file():
        return {"role": "user", "content": f"{user_message}\n\n(用户上传了 {code} 附件: {file_path}，但文件读取失败)"}

    suffix = local.suffix.lower()
    is_image = suffix in IMAGE_SUFFIXES
    if not is_image:
        return {"role": "user", "content": f"{user_message}\n\n(用户上传了 {code} {title}，附件: {file_path}，请让用户描述附件内容)"}

    # Path A: 直接 inline base64 (multimodal 模型直接看图)
    # v0.8.0: for_deep_thinking=True 时跳过, 避免 404
    if include_image and not for_deep_thinking:
        size = local.stat().st_size
        if size <= MAX_INLINE_IMAGE_SIZE:
            try:
                data = base64.b64encode(local.read_bytes()).decode("ascii")
                mime = MIME_MAP.get(suffix.lstrip("."), "jpeg")
                data_url = f"data:image/{mime};base64,{data}"
                content = [
                    {"type": "text", "text": f"{user_message}\n\n(参考 {code}: {title})"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
                logger.info(f"Inline image {local.name} ({size//1024}KB)")
                return {"role": "user", "content": content}
            except Exception as e:
                logger.warning(f"Failed to inline image: {e}")

    # Path B: 用 vision_client 先转文字再传
    # for_deep_thinking=True 时也走这里 (深推模型不支持图)
    if not image_description:
        ok, image_description, vision_model = await describe_top_image(top_resource)
        if not ok:
            # v0.8.0: vision 失败时明确告诉用户, 不要让 LLM 跑个空上下文幻觉回答
            logger.warning(f"Vision failed for {local.name}: {image_description}")
            return {
                "role": "user",
                "content": (
                    f"{user_message}\n\n"
                    f"(用户上传了 {code} {title} 附件: {local.name}，但读图模型全部不可用: {image_description}。\n"
                    f"请告诉用户: '我看不见你发的 {code} 图，能打个文字描述一下题面吗?'"
                    f")"
                ),
            }

    if image_description:
        return {
            "role": "user",
            "content": (
                f"{user_message}\n\n"
                f"(参考 {code}: {title}。\n"
                f"[图片描述]:\n{image_description})"
            ),
        }
    return {
        "role": "user",
        "content": f"{user_message}\n\n(用户上传了 {code} {title} 附件: {local.name}，但当前读图模型不可用，请基于上下文内容回答)"
    }
