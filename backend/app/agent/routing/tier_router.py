"""Tier Router - 根据复杂度选 LLM 档位
- 3 档: low / medium / high
- 每档有: primary 模型 + fallback 链
- 配置在 .env, 不在代码里写死
- 未来加: 动态成本感知路由, 限流感知路由等
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.agent.routing.classifier import (
    ComplexityClassifier,
    ClassificationResult,
    get_classifier,
)

logger = logging.getLogger(__name__)


@dataclass
class TierInfo:
    """一档模型的完整信息"""
    primary: str
    fallback: list[str]
    description: str
    tier_label: str  # "low" | "medium" | "high"


# 默认档位定义 — 用户指定 2026-07-28
# primary 严格按用户拍板: low=minimaxM3, mid=Z.ai GLM 5.2, high=Grok 4.20 Multi-Agent
# fallback 自己定 — OpenRouter 真实存在的模型, 失败时按顺序降级
# 实测 2026-07-28: 这个 OpenRouter 账号调不通 OpenAI / Anthropic / Google / Llama 4 (全 region 限)
#   但能调 xAI Grok 全系列 — Grok 4.20 = xAI 最新旗舰, Multi-Agent 模式 = 多智能体协作
#   (用户 2026-07-28 改用 Grok 4.20 Multi-Agent 顶 high 档)
DEFAULT_TIERS = {
    "low": TierInfo(
        primary="minimax/minimax-m3",
        fallback=["minimax/minimax-m2.7", "z-ai/glm-4.5-air", "deepseek/deepseek-chat-v3.1"],
        description="MiniMax M3 - 闲聊、简单查询、1-2 步任务 (国产便宜中文强)",
        tier_label="low",
    ),
    "medium": TierInfo(
        primary="z-ai/glm-5.2",
        fallback=["minimax/minimax-m2.7", "z-ai/glm-5-turbo", "deepseek/deepseek-chat-v3.1"],
        description="Z.ai GLM 5.2 - 标准问答、多步推理 (国产旗舰, 编码能力强)",
        tier_label="medium",
    ),
    "high": TierInfo(
        primary="x-ai/grok-4.20-multi-agent",
        fallback=["x-ai/grok-4.20", "x-ai/grok-4.5", "z-ai/glm-5.2", "z-ai/glm-5-turbo", "minimax/minimax-m2.7", "deepseek/deepseek-chat-v3.1"],
        description="Grok 4.20 Multi-Agent - 复杂规划/深度推理 (xAI 最新旗舰, 多智能体协作)",
        tier_label="high",
    ),
}


class TierRouter:
    """档位路由器
    - 内部维护 3 档配置
    - 提供 classify_and_route() 一步到位: 分类 + 选模型
    - 支持 force_tier 调试覆盖 (需要环境变量开关)
    """

    def __init__(self, classifier: Optional[ComplexityClassifier] = None):
        self.classifier = classifier
        self.tiers = self._load_tiers_from_env()
        # 是否允许客户端强制档位 (默认禁用, 防止成本攻击)
        self.allow_force_tier = os.environ.get("ZHAANG_DEBUG_FORCE_TIER") == "1"
        logger.info(
            f"TierRouter ready: low={self.tiers['low'].primary}, "
            f"medium={self.tiers['medium'].primary}, "
            f"high={self.tiers['high'].primary} "
            f"(force_tier={'enabled' if self.allow_force_tier else 'disabled'})"
        )

    def _load_tiers_from_env(self) -> dict[str, TierInfo]:
        """从 settings 读档位配置, 没有就 fallback 到 DEFAULT_TIERS"""
        def parse_fb(raw: str, default: list[str]) -> list[str]:
            if not raw:
                return default
            out = [m.strip() for m in raw.split(",") if m.strip()]
            return out if out else default

        return {
            "low": TierInfo(
                primary=settings.TIER_MODEL_LOW or DEFAULT_TIERS["low"].primary,
                fallback=parse_fb(settings.TIER_FALLBACK_LOW, DEFAULT_TIERS["low"].fallback),
                description=DEFAULT_TIERS["low"].description,
                tier_label="low",
            ),
            "medium": TierInfo(
                primary=settings.TIER_MODEL_MEDIUM or DEFAULT_TIERS["medium"].primary,
                fallback=parse_fb(settings.TIER_FALLBACK_MEDIUM, DEFAULT_TIERS["medium"].fallback),
                description=DEFAULT_TIERS["medium"].description,
                tier_label="medium",
            ),
            "high": TierInfo(
                primary=settings.TIER_MODEL_HIGH or DEFAULT_TIERS["high"].primary,
                fallback=parse_fb(settings.TIER_FALLBACK_HIGH, DEFAULT_TIERS["high"].fallback),
                description=DEFAULT_TIERS["high"].description,
                tier_label="high",
            ),
        }

    def get_tier(self, complexity: str) -> TierInfo:
        """获取某档配置 (兼容大小写 / 拼写错误)"""
        c = (complexity or "medium").strip().lower()
        if c in ("low", "easy", "simple", "l"):
            return self.tiers["low"]
        if c in ("high", "hard", "complex", "h"):
            return self.tiers["high"]
        return self.tiers["medium"]

    def get_model_for_complexity(self, complexity: str) -> tuple[str, list[str], TierInfo]:
        """返回 (primary_model, fallback_chain, tier_info)"""
        tier = self.get_tier(complexity)
        return tier.primary, tier.fallback, tier

    def all_models(self) -> list[str]:
        """所有档位用到的模型 (去重) — 给前端调试用"""
        seen = set()
        out = []
        for t in self.tiers.values():
            for m in [t.primary] + t.fallback:
                if m not in seen:
                    seen.add(m)
                    out.append(m)
        return out

    async def classify_and_route(
        self,
        user_message: str,
        history: Optional[list] = None,
        deep_thinking: bool = False,
        force_tier: Optional[str] = None,
    ) -> dict:
        """一步到位: 分类 + 选模型
        Args:
            user_message: 用户消息
            history: 历史消息
            deep_thinking: 是否深度思考 (这是 1 个必要条件, 不是充要)
            force_tier: 强制档位 (需 self.allow_force_tier=True)
        Returns: {
            "complexity", "primary_model", "fallback_models", "tier_info",
            "classification": ClassificationResult,
            "model_used": str (实际用到的, 失败 fallback 后会更新)
        }

        v0.8.0 高档触发规则 (用户 2026-07-28):
          high  = (deep_thinking ON) AND (分类结果 = high)  → high
          else  (任何 deep_thinking 状态)                    → 上限 mid
        - 跳闸机制: deep_thinking=True 但分类结果是 low/medium → 上限 mid
        - 开启深度思考但不复杂任务 → 不浪费 high 资源
        """
        # 强制档位 (调试用)
        if force_tier and self.allow_force_tier:
            tier = self.get_tier(force_tier)
            return {
                "complexity": force_tier,
                "primary_model": tier.primary,
                "fallback_models": tier.fallback,
                "tier_info": tier,
                "classification": ClassificationResult(
                    complexity=force_tier, category="forced", confidence=1.0,
                    reason="forced by client", model_used="forced", fallback=False,
                ),
            }

        # 跑分类 (这个无论如何都要跑, 拿到 task_complexity)
        cls = self.classifier or get_classifier()
        result = await cls.classify(user_message, history)
        task_complexity = result.complexity  # low / medium / high

        # v0.8.0: high 触发规则 = deep_thinking AND complexity=high
        if deep_thinking and task_complexity == "high":
            tier = self.get_tier("high")
            return {
                "complexity": "high",
                "primary_model": tier.primary,
                "fallback_models": tier.fallback,
                "tier_info": tier,
                "classification": ClassificationResult(
                    complexity="high", category="deep_thinking+high", confidence=1.0,
                    reason=f"deep_thinking=ON AND classifier=high (满足 high 双条件)",
                    model_used="forced", fallback=False,
                ),
            }

        # v0.8.0: 跳闸 — 任何未走 high 的情况, 上限 mid
        # - deep_thinking=ON 但 classifier=low/medium → 上限 mid
        # - deep_thinking=OFF 什么都不加 → 上限 mid
        # - classifier=high 但 deep_thinking=OFF → 上限 mid
        target_complexity = task_complexity
        if target_complexity == "high" and not deep_thinking:
            # 分类说 high 但用户没开深度思考 → 降档到 mid
            target_complexity = "medium"
            reason_suffix = " [high 被降级: 深度思考未开]"
        elif deep_thinking and target_complexity in ("low", "medium"):
            # 开了深度思考但任务不够复杂 → 保持原档, 不浪费 high 资源
            reason_suffix = ""
        else:
            reason_suffix = ""

        tier = self.get_tier(target_complexity)
        return {
            "complexity": target_complexity,
            "primary_model": tier.primary,
            "fallback_models": tier.fallback,
            "tier_info": tier,
            "classification": ClassificationResult(
                complexity=target_complexity,
                category=result.category,
                confidence=result.confidence,
                reason=result.reason + reason_suffix,
                model_used=result.model_used,
                fallback=result.fallback,
            ),
        }


# ===== 单例 =====

_router_singleton: Optional[TierRouter] = None


def get_tier_router() -> TierRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = TierRouter()
    return _router_singleton


async def classify_and_route(
    user_message: str,
    history: Optional[list] = None,
    deep_thinking: bool = False,
    force_tier: Optional[str] = None,
) -> dict:
    """便捷函数: 一步到位"""
    return await get_tier_router().classify_and_route(
        user_message, history, deep_thinking, force_tier,
    )
