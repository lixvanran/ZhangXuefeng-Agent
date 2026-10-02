"""Tavily 搜索 - 1000 次/月免费, AI 友好格式
"""
import logging
from typing import Dict

from app.core.config import settings
from app.agent.search.providers.base import search_result_template

logger = logging.getLogger(__name__)


async def tavily_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """Tavily API 调用. 需要 .env 里 TAVILY_API_KEY

    v0.10.0 修: 之前签名缺 `time_hint`, 而 web_search._try_provider_for_all_candidates
    无条件下发 `time_hint=` 关键字 → TypeError → 被宽 except 吞成 warning,
    导致 Tavily 自 v0.8.0 起 100% 静默死亡 (配了 key 也不生效)。
    """
    if not settings.TAVILY_API_KEY:
        return search_result_template("tavily", query) | {"error": "TAVILY_API_KEY not set"}
    try:
        import httpx
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": True,
        }
        # Tavily 用 `days` 限定新鲜度, 对应我们的 recency 提示
        if time_hint:
            recency = time_hint.get("recency")
            days = {"day": 1, "week": 7, "month": 31, "year": 365}.get(recency)
            if days:
                payload["days"] = days
                payload["topic"] = "news" if days <= 7 else "general"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json=payload,
            )
        if resp.status_code == 200:
            data = resp.json()
            results = [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                for r in data.get("results", [])
            ]
            # v0.10.0: 不再套 filter_chinese_results — Tavily 自带 AI 语义检索,
            # 对中文 query 返回的就是该给的内容; 之前的"只留含中文结果"过滤会
            # 把权威英文源误杀, 且常把结果过滤成空 → 等于白花钱。
            if results:
                return {
                    "success": True,
                    "provider": "tavily",
                    "query": query,
                    "answer": data.get("answer", ""),
                    "results": results,
                }
            return search_result_template("tavily", query) | {"error": "no results"}
        return search_result_template("tavily", query) | {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return search_result_template("tavily", query) | {"error": str(e)}
