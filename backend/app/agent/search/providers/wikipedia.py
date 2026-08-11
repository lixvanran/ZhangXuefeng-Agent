"""Wikipedia API 搜索 - 稳定 + 国内外都能调 + 中英文都有
API 文档: https://www.mediawiki.org/wiki/API:Search
REST endpoint: https://zh.wikipedia.org/w/api.php (中文) / https://en.wikipedia.org/w/api.php (英文)
"""
import logging
from typing import Dict

from app.agent.search.providers.base import search_result_template

logger = logging.getLogger(__name__)

# 优先中文 wiki, 失败 fallback 英文
WIKI_ENDPOINTS = [
    ("zh", "https://zh.wikipedia.org/w/api.php"),
    ("en", "https://en.wikipedia.org/w/api.php"),
]


async def wikipedia_search(query: str, max_results: int = 8, time_hint: dict = None) -> Dict:
    """Wikipedia 搜索
    - 返回每条的 title / url / content (摘要) / published
    - 中英双语, 先试中文再试英文
    - 国内外都能调 (无墙, API 稳定)
    """
    try:
        import httpx
        results = []
        tried_endpoints = []
        for lang, endpoint in WIKI_ENDPOINTS:
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": min(max_results, 10),
                "srprop": "snippet|titlesnippet",
                "utf8": "1",
                "origin": "*",
            }
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    resp = await client.get(
                        endpoint,
                        params=params,
                        headers={"User-Agent": "ZhangXueFengAgent/0.8 (educational; contact@example.com)"},
                    )
                tried_endpoints.append(f"{lang}({resp.status_code})")
                if resp.status_code != 200:
                    continue
                data = resp.json()
                search_results = data.get("query", {}).get("search", [])
                if search_results:
                    # 找到了就用这个语言, 不再试下一个
                    for r in search_results[:max_results]:
                        title = r.get("title", "")
                        url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        # snippet 是带 <span> 标签的 HTML, 去掉
                        import re as _re
                        snippet = _re.sub(r"<[^>]+>", "", r.get("snippet", ""))
                        # 拿到完整摘要 (调用 prop=extracts 拿 plain text)
                        results.append({
                            "title": title,
                            "url": url,
                            "content": snippet[:500],
                            "published": "",  # wiki 没有发布时间
                            "language": lang,
                        })
                    # 成功, 跳出循环
                    break
            except Exception as e:
                logger.warning(f"Wikipedia {lang} search failed: {e}")
                tried_endpoints.append(f"{lang}(err)")
                continue

        if results:
            # v0.8.0: 自动给每条加完整摘要 (extracts API 拿 plain text, 比 snippet 详细)
            results = await _enrich_with_extracts(results, max_results=5)
            return {
                "success": True,
                "provider": "wikipedia",
                "query": query,
                "results": results,
                "tried_endpoints": tried_endpoints,
            }
        return search_result_template("wikipedia", query) | {
            "error": f"no results (tried: {tried_endpoints})"
        }
    except Exception as e:
        logger.error(f"Wikipedia search error: {e}")
        return search_result_template("wikipedia", query) | {"error": str(e)}


async def _enrich_with_extracts(results: list, max_results: int = 5) -> list:
    """调 extracts API 拿每条的 plain text 摘要, 替换 snippet
    v0.8.0: 让 LLM 拿到的是干净的纯文本, 不要 HTML 标签
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            for r in results[:max_results]:
                # 从 url 推断语言和 endpoint
                if "/zh.wikipedia.org/" in r.get("url", ""):
                    endpoint = "https://zh.wikipedia.org/w/api.php"
                else:
                    endpoint = "https://en.wikipedia.org/w/api.php"
                title = r.get("title", "")
                if not title:
                    continue
                try:
                    resp = await client.get(
                        endpoint,
                        params={
                            "action": "query",
                            "format": "json",
                            "prop": "extracts",
                            "exintro": "1",  # 只要引言段
                            "explaintext": "1",  # 纯文本
                            "redirects": "1",  # 自动 follow 重定向
                            "titles": title,
                        },
                        headers={"User-Agent": "ZhangXueFengAgent/0.8 (educational)"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        pages = data.get("query", {}).get("pages", {})
                        for _, page in pages.items():
                            extract = page.get("extract", "")
                            if extract:
                                # 用 extract 替换 snippet, 截前 1000 字
                                r["content"] = extract[:1000]
                                r["full_extract_available"] = len(extract) > 1000
                                r["extract_total_chars"] = len(extract)
                                break
                except Exception:
                    pass  # 单条失败不影响整体
    except Exception as e:
        logger.warning(f"_enrich_with_extracts error: {e}")
    return results
