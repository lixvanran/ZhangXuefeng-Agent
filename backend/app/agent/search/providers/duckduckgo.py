"""DuckDuckGo 搜索 - 免费无 key, 英文较好

v0.10.0 修: 官方包已从 `duckduckgo_search` 改名为 `ddgs` (旧包停止维护,
新版本大量用户反馈 `duckduckgo_search` 直接 ModuleNotFoundError / 接口不兼容)。
这里同时兼容两种包名, 优先用新的 `ddgs`。
"""
import asyncio
import logging
from typing import Dict, List

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)


def _get_ddgs_class():
    """拿到 DDGS 类 — 兼容 ddgs(新) / duckduckgo_search(旧) 两种包名"""
    try:
        from ddgs import DDGS  # 新包名 (2024-11 起官方)
        return DDGS, "ddgs"
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # 旧包名
        return DDGS, "duckduckgo_search"
    except ImportError:
        return None, None


def _sync_ddg(query: str, max_results: int) -> List[Dict]:
    """同步版 DDG - 在 thread 跑避免阻塞 event loop"""
    DDGS, pkg = _get_ddgs_class()
    if DDGS is None:
        logger.error("DuckDuckGo 未安装: pip install ddgs (旧包名 duckduckgo_search 已废弃)")
        return []
    try:
        results = []
        # ddgs 与 duckduckgo_search 的 kwargs 略有差异, 用签名探测
        import inspect
        kwargs = {"max_results": max_results, "region": "cn-zh", "safesearch": "moderate"}
        try:
            if "backend" in inspect.signature(DDGS.text).parameters:
                kwargs["backend"] = "auto"
        except (ValueError, TypeError):
            pass
        with DDGS() as ddgs:
            for r in ddgs.text(query, **kwargs):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
        logger.debug(f"DDG[{pkg}] '{query[:30]}' -> {len(results)} 条")
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
