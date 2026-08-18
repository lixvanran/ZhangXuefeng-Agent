"""Complexity Classifier - 把用户问题分成 low / medium / high

接口 (Protocol): 任何实现 classify() 方法的类都能接入
- 未来加新分类器 (BERT, Ensemble, 用户自己写的) 只需实现一个方法
- 工厂函数 get_classifier() 根据配置返回对应实现

当前实现:
- MiniMaxM3Classifier: 调 LLM (默认, 走 minimax/minimax-m3, 便宜中文强)
- HeuristicClassifier: 纯关键词启发式, 零 API 调用 (fallback)
- EnsembleClassifier: 多个分类器投票 (高准确, 成本也高)
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Protocol, runtime_checkable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """分类结果 - 标准化输出, 不管哪个分类器都返回这个"""
    complexity: str  # "low" | "medium" | "high"
    category: str    # greeting / chitchat / simple_lookup / fact_check / analysis / multi_step_planning / professional_advice / deep_reasoning / creative_writing / general
    confidence: float  # 0.0-1.0
    reason: str
    model_used: str
    fallback: bool = False
    # 调试用: 这次分类的耗时
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class ComplexityClassifier(Protocol):
    """分类器接口 - 所有实现必须满足这个契约"""

    async def classify(
        self,
        user_message: str,
        history: Optional[list] = None,
    ) -> ClassificationResult:
        """评估问题复杂度
        Args:
            user_message: 用户当前消息
            history: 历史消息 [{role, content}, ...], 可空
        Returns:
            ClassificationResult
        """
        ...


# ===== MiniMax-M3 分类器 (默认, 调 LLM) =====

CLASSIFY_SYSTEM_PROMPT = """You are a query complexity classifier. Analyze the user's question and return ONLY a JSON object.

# Classification rules

## "low" (简单任务 - 用国产高性价比模型)
- 闲聊问候: "你好", "你是谁", "今天天气"
- 简单事实查询: 1 步就能回答
- 不需要多步推理或长篇分析
- 用户表示不确定 / 不想深入: "随便问问"

## "medium" (中等任务 - 用 Claude Sonnet)
- 标准问答: 需要一些上下文知识
- 带具体数据的**随口一问**: "湖北620想学AI", "河南理科650报哪里"
  - 这种情况给个**简短建议 + 1-2 个方向**就够, 问用户"要不要展开冲稳保"
  - 不主动展开成 2000 字长文
- 通用建议: "什么是好专业", "考研难吗"
- 短分析 (1-2 段)
- 不需要查数据库/调工具

## "high" (复杂任务 - 用 Claude Sonnet 旗舰)
- **用户显式要求展开**: "详细分析", "展开讲", "给我冲稳保方案", "完整规划", "全帮我看看"
- **多步规划** + 用户明确要执行: "650分怎么报, 给我完整方案", "高考时间表, 一天一天安排"
- 深度推理 + 用户要长文: 涉及多因素权衡 + 明确要详细
- 用户连续追问 3 轮以上同一个话题 (说明真要深入)
- 涉及专业领域复杂决策 + 明确要长文分析

# ⚠️ 关键判断:
- "X分想学Y" → 默认 medium (随口问, 简短回答 + 问要不要展开)
- "X分想学Y, 详细说说/冲稳保/给我完整方案" → high (用户明确要展开)
- 没明确信号 = medium, 不主动开 long-form analysis

# Output format (ONLY this JSON, nothing else)
{
  "complexity": "low" | "medium" | "high",
  "category": "<one of: greeting, chitchat, simple_lookup, fact_check, analysis, multi_step_planning, professional_advice, deep_reasoning, creative_writing>",
  "confidence": <0.0-1.0>,
  "reason": "<1 sentence in Chinese, why this tier>"
}
"""


class MiniMaxM3Classifier:
    """用 MiniMax-M3 模型 (轻量便宜中文强) 做复杂度分类
    - 走 OpenRouter 统一入口, 一把 Key 即可
    - 失败时返回 None, 上层 fallback 到启发式
    - 内置 LRU 缓存: 相同问题 5 分钟内复用结果
    """

    # 默认模型: minimax/minimax-m3 (用户指定; OpenRouter 上可能叫别的, 改 .env 即可)
    DEFAULT_MODEL = "minimax/minimax-m3"

    def __init__(self, model: Optional[str] = None, ttl: int = 300, max_cache: int = 256):
        self.model = model or settings.CLASSIFY_MODEL or self.DEFAULT_MODEL
        self.ttl = ttl
        self.max_cache = max_cache
        self._cache: dict[str, tuple[float, ClassificationResult]] = {}

    def _cache_key(self, msg: str, history: Optional[list]) -> str:
        # 只用最近 1 轮 history 作 key, 避免组合爆炸
        h = ""
        if history:
            last = history[-1] if history else {}
            h = f"{last.get('role', '')}:{last.get('content', '')[:80]}"
        return f"{msg[:200]}|{h}"

    def _cache_get(self, key: str) -> Optional[ClassificationResult]:
        item = self._cache.get(key)
        if not item:
            return None
        ts, val = item
        if time.time() - ts > self.ttl:
            self._cache.pop(key, None)
            return None
        return val

    def _cache_set(self, key: str, val: ClassificationResult) -> None:
        if len(self._cache) >= self.max_cache:
            for k in list(self._cache.keys())[: self.max_cache // 4]:
                self._cache.pop(k, None)
        self._cache[key] = (time.time(), val)

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return None

    async def classify(
        self,
        user_message: str,
        history: Optional[list] = None,
    ) -> Optional[ClassificationResult]:
        """返回 ClassificationResult 或 None (失败时)
        None 触发上层 fallback 到 HeuristicClassifier
        """
        msg = (user_message or "").strip()
        if not msg:
            return ClassificationResult(
                complexity="low", category="empty", confidence=1.0,
                reason="空消息", model_used="n/a", fallback=True,
            )

        # 查缓存
        key = self._cache_key(msg, history)
        cached = self._cache_get(key)
        if cached:
            return cached

        # 拼 messages
        messages = [{"role": "system", "content": CLASSIFY_SYSTEM_PROMPT}]
        if history:
            for h in history[-2:]:
                messages.append(h)
        messages.append({"role": "user", "content": msg})

        t0 = time.time()
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.LLM_API_KEY or "dummy-key",
                base_url=settings.LLM_BASE_URL,
                default_headers=self._build_headers(),
            )
            resp = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200,
                temperature=0.1,
            )
            text = (resp.choices[0].message.content or "") if resp.choices else ""
            parsed = self._extract_json(text)
            if parsed and "complexity" in parsed:
                c = str(parsed["complexity"]).lower().strip()
                if c not in ("low", "medium", "high"):
                    c = "medium"
                result = ClassificationResult(
                    complexity=c,
                    category=str(parsed.get("category", "general")),
                    confidence=float(parsed.get("confidence", 0.5)),
                    reason=str(parsed.get("reason", ""))[:200],
                    model_used=self.model,
                    fallback=False,
                    elapsed_ms=int((time.time() - t0) * 1000),
                )
                self._cache_set(key, result)
                return result
            logger.warning(f"MiniMaxM3Classifier: non-JSON output: {text[:100]}")
        except Exception as e:
            logger.warning(f"MiniMaxM3Classifier failed: {e}")

        return None  # 触发 fallback

    @staticmethod
    def _build_headers() -> dict:
        # OpenRouter 推荐的 headers
        if "openrouter.ai" in settings.LLM_BASE_URL:
            return {
                "HTTP-Referer": settings.OPENROUTER_REFERER,
                "X-Title": settings.OPENROUTER_TITLE,
            }
        return {}


# ===== 启发式分类器 (无 API 调用, 兜底) =====

class HeuristicClassifier:
    """基于关键词的复杂度判断
    - 零 API 调用, 永远可用
    - 高 confidence 的情况直接出结果
    - 低 confidence 返回 medium (让上层走 fallback 链)
    """

    GREETING_WORDS = ["你好", "hi", "hello", "嗨", "在吗", "你是", "哈喽", "hey"]
    SIMPLE_LOOKUP_WORDS = ["什么是", "多少分", "哪一年", "几号", "是谁", "在哪", "怎么读"]
    # v0.8.0 修复: "帮我" / "建议" 单独出现其实是简单请求, 不应判 high
    # 比如 "帮我看看错题本" / "建议你推荐个专业" — 是用户对 AI 的常规请求, 不算规划
    # 真正的多步规划关键词是 "怎么规划" / "方案" / "如何准备" 加上"志愿/专业/学校"等明确领域
    PLANNING_WORDS = ["怎么报", "怎么选", "怎么规划", "志愿方案", "填报方案", "选科方案", "如何准备", "长远规划", "职业规划"]
    MEDIUM_WORDS = ["帮我", "建议", "推荐", "看看", "介绍", "讲讲", "说说", "分析下", "评估", "怎么样"]
    ANALYSIS_WORDS = ["为什么", "深度分析", "对比", "比较", "优缺点", "利弊", "深度对比"]

    def __init__(self, high_confidence_threshold: float = 0.7):
        self.high_confidence_threshold = high_confidence_threshold

    async def classify(
        self,
        user_message: str,
        history: Optional[list] = None,
    ) -> ClassificationResult:
        msg = (user_message or "").strip()
        n = len(msg)

        if n == 0:
            return ClassificationResult("low", "empty", 1.0, "空消息", "heuristic", True)

        if n < 8 and any(w in msg for w in self.GREETING_WORDS):
            return ClassificationResult("low", "greeting", 0.8, "短问候语", "heuristic", True)

        if n < 15 and any(w in msg for w in self.SIMPLE_LOOKUP_WORDS):
            return ClassificationResult("low", "simple_lookup", 0.7, "短事实查询", "heuristic", True)

        # v0.8.0: PLANNING_WORDS 出现才判 high (真正的多步规划/方案)
        if any(w in msg for w in self.PLANNING_WORDS):
            return ClassificationResult("high", "multi_step_planning", 0.75, "含规划关键词", "heuristic", True)

        # v0.8.0 新增: 单独的 "帮我/建议/推荐" 这种是 medium (常规问答)
        if any(w in msg for w in self.MEDIUM_WORDS):
            return ClassificationResult("medium", "general_request", 0.7, "含常规请求词", "heuristic", True)

        if any(w in msg for w in self.ANALYSIS_WORDS):
            return ClassificationResult("high", "analysis", 0.65, "含分析关键词", "heuristic", True)

        if n > 80:
            return ClassificationResult("medium", "analysis", 0.6, "长问题需要分析", "heuristic", True)

        if n > 30:
            return ClassificationResult("medium", "general", 0.5, "中等长度", "heuristic", True)

        return ClassificationResult("medium", "general", 0.4, "默认 medium", "heuristic", True)


# ===== Ensemble 分类器 (投票机制, 高准确高成本) =====

class EnsembleClassifier:
    """多分类器投票 - 同时跑多个, 多数决
    成本: 多次 API 调用
    收益: confidence 高, 适合生产环境对准确度敏感的场景
    """

    def __init__(self, classifiers: list[ComplexityClassifier]):
        self.classifiers = classifiers

    async def classify(
        self,
        user_message: str,
        history: Optional[list] = None,
    ) -> ClassificationResult:
        import asyncio
        results = await asyncio.gather(
            *[c.classify(user_message, history) for c in self.classifiers],
            return_exceptions=True,
        )
        # 过滤异常和 None
        valid = [r for r in results if isinstance(r, ClassificationResult)]
        if not valid:
            # 全挂, 退到启发式兜底
            fb = HeuristicClassifier()
            return await fb.classify(user_message, history)

        # 投票: 算每个 complexity 的加权 confidence
        scores: dict[str, float] = {"low": 0.0, "medium": 0.0, "high": 0.0}
        for r in valid:
            scores[r.complexity] += r.confidence
        winner = max(scores, key=lambda k: scores[k])
        total = sum(scores.values()) or 1.0
        return ClassificationResult(
            complexity=winner,
            category=valid[0].category,
            confidence=round(scores[winner] / total, 3),
            reason=f"Ensemble vote ({len(valid)} classifiers): {winner}",
            model_used=f"ensemble({','.join(r.model_used for r in valid)})",
            fallback=False,
        )


# ===== 工厂: 根据配置返回合适的分类器 =====

_classifier_singleton: Optional[ComplexityClassifier] = None


def get_classifier() -> ComplexityClassifier:
    """获取分类器单例
    优先级: 1) 指定的 LLM 分类器  2) 启发式 (LLM 不可用时)"""
    global _classifier_singleton
    if _classifier_singleton is not None:
        return _classifier_singleton

    primary = MiniMaxM3Classifier()
    heuristic = HeuristicClassifier()

    # 用 wrapper 实现 fallback chain
    class FallbackClassifier:
        def __init__(self, primary, fallback):
            self.primary = primary
            self.fallback = fallback

        async def classify(self, user_message, history=None):
            result = await self.primary.classify(user_message, history)
            if result is None:
                logger.debug("Primary classifier failed, using heuristic fallback")
                return await self.fallback.classify(user_message, history)
            return result

    _classifier_singleton = FallbackClassifier(primary, heuristic)
    return _classifier_singleton
