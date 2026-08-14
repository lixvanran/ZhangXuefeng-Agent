"""模型白名单 - v0.9.1 新增
- 严格白名单: 路由只能调用这里列的模型 (用户 2026-08-11 拍板)
- 任何不在白名单的模型 ID 会被 settings API 拒绝, 路由层也会兜底校验
- 默认值: 用户首次打开时的初始选择

用户规则 (2026-08-11):
- low: qwen-2.5-7b / minimax-m2.7 / deepseek-v3.1
- mid: minimax-m3 / glm-5 / deepseek-v4-flash
- high: minimax-m3 / grok-4.20-multi-agent / glm-5.2 / deepseek-v4-pro
- 默认: low=minimax-m2.7, mid=minimax-m3, high=minimax-m3
- 调用规则: high 档需要 (分类=high) AND (high 模式=开), 否则最多 mid
"""
from typing import Dict, List


# ===== 白名单 (严格, 路由只能用这里列的) =====

MODEL_WHITELIST: Dict[str, List[str]] = {
    "low": [
        "qwen/qwen-2.5-7b-instruct",        # 千问 7b
        "minimax/minimax-m2.7",              # minimaxM2.7
        "deepseek/deepseek-chat-v3.1",       # deepseek V3
    ],
    "medium": [
        "minimax/minimax-m3",                # minimaxM3
        "z-ai/glm-5",                        # GLM 5
        "deepseek/deepseek-v4-flash",        # deepseek V4-Flash
    ],
    "high": [
        "minimax/minimax-m3",                # minimaxM3
        "x-ai/grok-4.20-multi-agent",        # grok 4.20 multi-agent 顶配
        "z-ai/glm-5.2",                      # GLM 5.2 顶配
        "deepseek/deepseek-v4-pro",          # deepseek V4-Pro 顶配
    ],
}


# ===== 默认值 (用户首次进入时的初始选择) =====

DEFAULT_TIER_MODELS: Dict[str, str] = {
    "low": "minimax/minimax-m2.7",
    "medium": "minimax/minimax-m3",
    "high": "minimax/minimax-m3",
}


# ===== 档位展示信息 (前端用) =====

TIER_LABELS: Dict[str, str] = {
    "low": "low (闲聊 / 简单查询)",
    "medium": "medium (标准问答)",
    "high": "high (复杂规划 / 深度推理)",
}


def is_model_allowed(tier: str, model: str) -> bool:
    """校验模型是否在该档白名单内"""
    return tier in MODEL_WHITELIST and model in MODEL_WHITELIST[tier]
