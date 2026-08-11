"""DuckDuckGo 搜索 - 免费无 key, 英文较好
"""
import asyncio
import logging
from typing import Dict, List

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)


def _sync_ddg(query: str, max_results: int) -> List[Dict]:
    """同步版 DDG - 在 thread 跑避免阻塞 event loop"""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, region="cn-zh", safesearch="moderate"):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
        return results
    except Exception as e:
        logger.error(f"DDG sync error: {e}")
        return []


async def duckduckgo_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """异步版 - 用 asyncio.to_thread 跑同步 DDG"""
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(_sync_ddg, query, max_results),
            timeout=15.0,
        )
        if results:
            results = filter_chinese_results(results)
            if results:
                return {"success": True, "provider": "duckduckgo", "query": query, "results": results}
        return search_result_template("duckduckgo", query) | {"error": "no results"}
    except asyncio.TimeoutError:
        return search_result_template("duckduckgo", query) | {"error": "timeout"}
    except Exception as e:
        return search_result_template("duckduckgo", query) | {"error": str(e)}
