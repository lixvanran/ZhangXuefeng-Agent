"""Baidu HTML 抓取 - 国内可用, 但常验证码
"""
import logging
from urllib.parse import quote_plus
from typing import Dict

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)


async def baidu_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """Baidu HTML 抓取"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        url = f"https://www.baidu.com/s?wd={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return search_result_template("baidu", query) | {"error": f"HTTP {resp.status_code}"}
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for container in soup.select("div.result, div.c-container, div.result-op"):
            title_el = container.select_one("h3 a, h3, a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "") if title_el.name == "a" else ""
            abstract_el = container.select_one(".c-abstract, .content-abstract")
            content = abstract_el.get_text(strip=True) if abstract_el else ""
            if not content:
                content = container.get_text(" ", strip=True)[:200]
            if title and title not in ("百度一下", "百度首页"):
                results.append({"title": title, "url": href, "content": content[:300]})
            if len(results) >= max_results:
                break
        if results:
            results = filter_chinese_results(results)
            if results:
                return {"success": True, "provider": "baidu", "query": query, "results": results}
        return search_result_template("baidu", query) | {"error": "no results"}
    except Exception as e:
        logger.error(f"Baidu error: {e}")
        return search_result_template("baidu", query) | {"error": str(e)}
