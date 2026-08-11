"""arXiv API 搜索 - 论文 / 学术资料专用
API 文档: https://arxiv.org/help/api
REST endpoint: http://export.arxiv.org/api/query (返回 Atom XML)
国内外都能调 (无墙)
"""
import logging
import xml.etree.ElementTree as ET
from typing import Dict
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


async def arxiv_search(query: str, max_results: int = 5, time_hint: dict = None) -> Dict:
    """arXiv 学术论文搜索
    - 用 arxiv 官方 API (无需 key, 无墙)
    - 返回 Atom XML, 我们解析
    - 默认按相关度排序
    """
    try:
        import httpx
        url = (
            f"http://export.arxiv.org/api/query?"
            f"search_query=all:{quote_plus(query)}&"
            f"start=0&max_results={min(max_results, 10)}&"
            f"sortBy=relevance&sortOrder=descending"
        )
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "ZhangXueFengAgent/0.8 (educational)"},
            )
        if resp.status_code != 200:
            return {
                "success": False,
                "provider": "arxiv",
                "query": query,
                "results": [],
                "error": f"HTTP {resp.status_code}",
            }

        # 解析 Atom XML
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        root = ET.fromstring(resp.text)
        results = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            id_el = entry.find("atom:id", ns)
            published_el = entry.find("atom:published", ns)
            author_els = entry.findall("atom:author", ns)
            authors = [
                a.find("atom:name", ns).text.strip()
                for a in author_els
                if a.find("atom:name", ns) is not None
            ]
            # 抓分类 (subject)
            cat_el = entry.find("arxiv:primary_category", ns)
            category = cat_el.get("term", "") if cat_el is not None else ""

            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            summary = (summary_el.text or "").strip() if summary_el is not None else ""
            url = (id_el.text or "").strip() if id_el is not None else ""
            published = (published_el.text or "")[:10] if published_el is not None else ""

            if not title:
                continue
            results.append({
                "title": title,
                "url": url,
                "content": summary[:800],
                "published": published,
                "authors": ", ".join(authors[:3]) + ("等" if len(authors) > 3 else ""),
                "category": category,
            })
        if results:
            return {
                "success": True,
                "provider": "arxiv",
                "query": query,
                "results": results,
            }
        return {
            "success": False,
            "provider": "arxiv",
            "query": query,
            "results": [],
            "error": "no results from arxiv",
        }
    except Exception as e:
        logger.error(f"arXiv search error: {e}")
        return {
            "success": False,
            "provider": "arxiv",
            "query": query,
            "results": [],
            "error": str(e),
        }
