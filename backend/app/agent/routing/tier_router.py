"""Tier Router - 根据复杂度选 LLM 档位
- 3 档: low / medium / high
- 每档有: primary 模型 + fallback 链
- v0.9.1: primary 改成读用户偏好 (DB), 不再硬编码
- 白名单严格按用户 2026-08-11 拍板
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
from app.agent.routing.model_whitelist import (
    MODEL_WHITELIST,
    DEFAULT_TIER_MODELS,
    is_model_allowed,
)

logger = logging.getLogger(__name__)


@dataclass
class TierInfo:
    """一档模型的完整信息"""
    primary: str
    fallback: list[str]
    description: str
    tier_label: str  # "low" | "medium" | "high"


# 默认档位定义 (用户 2026-08-11 拍板)
# low=minimaxM2.7 (默认), mid=minimaxM3, high=minimaxM3
# 实际值从 model_whitelist.DEFAULT_TIER_MODELS 读
# fallback 链按白名单内其他模型降级
DEFAULT_TIERS = {
    "low": TierInfo(
        primary=DEFAULT_TIER_MODELS["low"],
        fallback=[m for m in MODEL_WHITELIST["low"] if m != DEFAULT_TIER_MODELS["low"]],
        description="闲聊 / 简单查询 / 1-2 步任务",
        tier_label="low",
    ),
    "medium": TierInfo(
        primary=DEFAULT_TIER_MODELS["medium"],
        fallback=[m for m in MODEL_WHITELIST["medium"] if m != DEFAULT_TIER_MODELS["medium"]],
        description="标准问答 / 多步推理",
        tier_label="medium",
    ),
    "high": TierInfo(
        primary=DEFAULT_TIER_MODELS["high"],
        fallback=[m for m in MODEL_WHITELIST["high"] if m != DEFAULT_TIER_MODELS["high"]],
        description="复杂规划 / 深度推理 (需开启 high 模式)",
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
        """v0.9.1: 从用户偏好 (DB) 读档位配置, 兜底用白名单默认值

        加载顺序:
        1. DB user_preferences 表 (用户在前端"系统设置"改的)
        2. 白名单默认值 (model_whitelist.DEFAULT_TIER_MODELS)
        3. 兜底校验: 不在白名单的模型 fallback 到默认
        """
        from app.db.database import SessionLocal, UserPreferenceORM

        def read_user_pref(key: str, default: str) -> str:
            """从 DB 读用户偏好, 找不到或不在白名单就 return default"""
            try:
                db = SessionLocal()
                try:
                    row = db.query(UserPreferenceORM).filter_by(
                        user_id=1, key=key
                    ).first()
                    if row and row.value:
                        model = row.value if isinstance(row.value, str) else str(row.value)
                        # 兜底: 必须在该档白名单内
                        tier = key.replace("model_", "")
                        if is_model_allowed(tier, model):
                            return model
                        else:
                            logger.warning(
                                f"User pref {key}={model} not in whitelist, "
                                f"fallback to default"
                            )
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Failed to read user pref {key}: {e}")
            return default

        def build_fallback(tier: str, primary: str) -> list[str]:
            """从白名单构建 fallback 链 (排除 primary)"""
            return [m for m in MODEL_WHITELIST[tier] if m != primary]

        return {
            "low": TierInfo(
                primary=read_user_pref("model_low", DEFAULT_TIER_MODELS["low"]),
                fallback=build_fallback("low", read_user_pref("model_low", DEFAULT_TIER_MODELS["low"])),
                description=DEFAULT_TIERS["low"].description,
                tier_label="low",
            ),
            "medium": TierInfo(
                primary=read_user_pref("model_medium", DEFAULT_TIER_MODELS["medium"]),
                fallback=build_fallback("medium", read_user_pref("model_medium", DEFAULT_TIER_MODELS["medium"])),
                description=DEFAULT_TIERS["medium"].description,
                tier_label="medium",
            ),
            "high": TierInfo(
                primary=read_user_pref("model_high", DEFAULT_TIER_MODELS["high"]),
                fallback=build_fallback("high", read_user_pref("model_high", DEFAULT_TIER_MODELS["high"])),
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
