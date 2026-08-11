"""Agent Routing Module - 问题复杂度分析 + 模型档位路由

设计目标 (为未来扩展预留接口):
- Classifier (分类器): 把用户问题分成 low/medium/high
  - 当前实现: MiniMaxM3Classifier (默认, 调 LLM) + HeuristicClassifier (无 API 兜底)
  - 未来加: EnsembleClassifier, BertClassifier 等
- TierRouter (档位路由器): 根据复杂度选模型
  - 当前实现: 三档静态配置 (low/medium/high → 主+fallback 链)
  - 未来加: 动态成本感知路由, A/B 测试路由等
- ModelProvider (LLM provider 抽象):
  - 当前实现: OpenRouter (一把 Key 通吃所有模型)
  - 未来加: 直连 Anthropic SDK, 直连 DeepSeek SDK, Azure OpenAI 等

Public API:
- get_classifier()       → ComplexityClassifier (单例)
- get_tier_router()      → TierRouter (单例)
- classify_and_route()   → 一步到位: 分类 + 选模型
"""
from app.agent.routing.classifier import (
    ComplexityClassifier,
    ClassificationResult,
    MiniMaxM3Classifier,
    HeuristicClassifier,
    EnsembleClassifier,
    get_classifier,
)
from app.agent.routing.tier_router import (
    TierRouter,
    TierInfo,
    get_tier_router,
    classify_and_route,
)

__all__ = [
    "ComplexityClassifier",
    "ClassificationResult",
    "MiniMaxM3Classifier",
    "HeuristicClassifier",
    "EnsembleClassifier",
    "get_classifier",
    "TierRouter",
    "TierInfo",
    "get_tier_router",
    "classify_and_route",
]
