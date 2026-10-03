"""360 搜索 (so.com) - 中文, 无需 key

2026-10-02 实测: 对多 term 中文查询表现明显优于 Bing。
实测「人工智能专业 就业前景 怎么样」词覆盖率 100%,
「强基计划 报考条件」50%。

同样有反爬, 因此带进程内最小请求间隔。
"""
import asyncio
import logging
import time
from typing import Dict, List

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)

MIN_INTERVAL_SEC = 2.0
_last_request_at = 0.0
_lock = asyncio.Lock()


async def _throttle():
    global _last_request_at
    async with _lock:
        wait = _last_request_at + MIN_INTERVAL_SEC - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


def _so360_sync(query: str) -> List[Dict]:
    import urllib.parse
    import urllib.request
    import ssl
    import re as _re
    import html as _html

    url = "https://www.so.com/s?q=" + urllib.parse.quote(query)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
        body = r.read().decode("utf-8", "ignore")

    if len(body) < 50_000:
        logger.warning("360 返回内容异常短 (len=%d), 可能被拦", len(body))
        return []

    def clean(s):
        return _html.unescape(_re.sub(r"<[^>]+>", "", s)).strip()

    # 同 sogou: 只取 <a> 的文字, 并抓 href(360 还会在 a 上放 data-mdurl 存真实地址)
    out = []
    for m in _re.finditer(
            r'<h3[^>]*class="res-title"[^>]*>\s*<a([^>]*)>(.*?)</a>', body, _re.S):
        attrs, title = m.group(1), clean(m.group(2))
        href = ""
        hm = _re.search(r'data-mdurl="([^"]+)"', attrs) or _re.search(r'href="([^"]+)"', attrs)
        if hm:
            href = hm.group(1)
            if href.startswith("/"):
                href = "https://www.so.com" + href
        if title:
            out.append({"title": title, "url": href, "content": ""})
    return out


async def so360_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """360 搜索。只取标题, 摘要交由上层 fetch_url 补。"""
    try:
        await _throttle()
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, _so360_sync, query), timeout=15.0)
        if not results:
            return search_result_template("so360", query) | {"error": "no results or blocked"}
        results = results[:max_results]
        results = filter_chinese_results(results)
        if results:
            return {"success": True, "provider": "so360", "query": query, "results": results}
        return search_result_template("so360", query) | {"error": "no results"}
    except asyncio.TimeoutError:
        return search_result_template("so360", query) | {"error": "timeout"}
    except Exception as e:
        logger.error(f"360 搜索失败: {e}")
        return search_result_template("so360", query) | {"error": str(e)[:100]}
