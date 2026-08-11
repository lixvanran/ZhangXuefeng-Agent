"""Tavily 搜索 - 1000 次/月免费, AI 友好格式
"""
import logging
from typing import Dict

from app.core.config import settings
from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)


async def tavily_search(query: str, max_results: int = 10) -> Dict:
    """Tavily API 调用. 需要 .env 里 TAVILY_API_KEY"""
    if not settings.TAVILY_API_KEY:
        return search_result_template("tavily", query) | {"error": "TAVILY_API_KEY not set"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": True,
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            results = [
                {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
                for r in data.get("results", [])
            ]
            results = filter_chinese_results(results)
            return {
                "success": bool(results),
                "provider": "tavily",
                "query": query,
                "answer": data.get("answer", ""),
                "results": results,
            }
        return search_result_template("tavily", query) | {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return search_result_template("tavily", query) | {"error": str(e)}
