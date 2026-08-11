"""Bing HTML 抓取 - cn.bing.com 无验证码, CN 友好
"""
import logging
from urllib.parse import quote_plus
from typing import Dict

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)


async def bing_html_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """Scrape cn.bing.com HTML"""
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        url = f"https://cn.bing.com/search?q={quote_plus(query)}&setlang=zh-Hans&cc=CN&count=30"
        if time_hint:
            recency = time_hint.get("recency")
            if recency == "day":
                url += "&qft=+filter:day"
            elif recency == "week":
                url += "&qft=+filter:week"
            elif recency == "month":
                url += "&qft=+filter:month"
            elif recency == "year":
                url += "&qft=+filter:year"
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return search_result_template("bing", query) | {"error": f"HTTP {resp.status_code}"}

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        containers = soup.select("li.b_algo, li.b_algoLi, .b_algo, .b_results li, ol#b_results > li")
        if not containers:
            containers = soup.select("li")
        for li in containers:
            h2 = li.select_one("h2, h3, .b_title")
            if not h2:
                continue
            a = h2.find("a") or li.select_one("a.tilk, a.title")
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not href or not href.startswith("http"):
                continue
            content = ""
            for sel in [".b_caption p", ".b_snippet", ".b_algoSlug", ".b_paractl", "p.b_lineclamp", ".b_caption", "p"]:
                p = li.select_one(sel)
                if p:
                    txt = p.get_text(" ", strip=True)
                    if len(txt) > 20 and txt != title:
                        content = txt
                        break
            if not content:
                full = li.get_text(" ", strip=True)
                if title and full.startswith(title):
                    full = full[len(title):].strip()
                content = full[:300]
            pub = ""
            for sel in [".b_factrow span", ".news_dt", "span.news_dt", ".b_caption .b_attribution", "cite"]:
                el = li.select_one(sel)
                if el:
                    pub = el.get_text(" ", strip=True)
                    break
            if title and title not in ("", "Bing", "必应") and len(title) < 200:
                results.append({
                    "title": title,
                    "url": href,
                    "content": content[:400],
                    "published": pub[:50] if pub else "",
                })
            if len(results) >= max_results:
                break
        if not results:
            for a in soup.select("h2 a, h3 a"):
                href = a.get("href", "")
                title = a.get_text(strip=True)
                if not href or not href.startswith("http"):
                    continue
                if title and title not in ("Bing", "必应", "") and len(title) < 200:
                    results.append({"title": title, "url": href, "content": "", "published": ""})
                if len(results) >= max_results:
                    break
        if results:
            results = filter_chinese_results(results)
            if results:
                return {"success": True, "provider": "bing", "query": query, "results": results}
        return search_result_template("bing", query) | {"error": "no results"}
    except Exception as e:
        logger.error(f"Bing HTML error: {e}")
        return search_result_template("bing", query) | {"error": str(e)}
