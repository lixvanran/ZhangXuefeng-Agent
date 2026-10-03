"""搜狗搜索 - 中文多词查询表现最好, 无需 key

2026-10-02 实测(同一台机器、同一网络、同一批查询):

| 查询                              | Bing  | Baidu | 搜狗  | 360   |
|-----------------------------------|-------|-------|-------|-------|
| 强基计划 报考条件                   |   0%  | 限流  | 100%  |  50%  |
| 人工智能专业 就业前景 怎么样           |   0%  | 限流  | ——   | 100%  |
| 广东 2025 高考一本线 多少分           |  25%  | 限流  | ——   |  50%  |

Bing 对多 term 中文查询会退化成只匹配第一个词(返回"汉字'强'的字典页"),
Baidu 对云 IP 硬限流。搜狗/360 明显更贴合本产品的中文场景。

注意: 搜狗有反爬(antispider 页), 连续请求会触发。
本模块因此带一个**进程内最小请求间隔**, 不要在别处直接调底层 httpx。
"""
import asyncio
import logging
import time
from typing import Dict, List

from app.agent.search.providers.base import search_result_template, filter_chinese_results

logger = logging.getLogger(__name__)

# 同一进程内两次请求的最小间隔(秒)。实测连续快速请求会触发 antispider。
MIN_INTERVAL_SEC = 2.5
_last_request_at = 0.0
_lock = asyncio.Lock()


async def _throttle():
    global _last_request_at
    async with _lock:
        now = time.monotonic()
        wait = _last_request_at + MIN_INTERVAL_SEC - now
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


def _sogou_sync(query: str) -> List[Dict]:
    import urllib.parse
    import urllib.request
    import ssl
    import re as _re
    import html as _html

    url = "https://www.sogou.com/web?query=" + urllib.parse.quote(query)
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

    # 反爬页: 内容极短或含验证码标记
    if len(body) < 50_000 or "antispider" in body or "请输入验证码" in body:
        logger.warning("搜狗触发反爬 (len=%d), 建议调大 MIN_INTERVAL_SEC", len(body))
        return []

    def clean(s):
        return _html.unescape(_re.sub(r"<[^>]+>", "", s)).strip()

    # 只取 <h3> 里的 <a>: h3 内除标题外还有图标 span 等元素,
    # 整个 h3 剥标签会把那些残留文字混进标题(实测出现"的是什麼? —教育在线 强基计划 报名条件")
    out = []
    for m in _re.finditer(
            r'<h3[^>]*class="vr-title"[^>]*>\s*<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            body, _re.S):
        href, title = m.group(1), clean(m.group(2))
        if title:
            if href.startswith("/"):
                href = "https://www.sogou.com" + href
            out.append({"title": title, "url": href, "content": ""})
    return out


async def sogou_search(query: str, max_results: int = 10, time_hint: dict = None) -> Dict:
    """搜狗搜索。

    只取标题做相关性判断与排序 —— 摘要抽取依赖页面结构, 变动频繁,
    贸然解析反而容易抓到脏数据。需要正文时由上层 fetch_url 补。
    """
    try:
        await _throttle()
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(None, _sogou_sync, query), timeout=15.0)
        if not results:
            return search_result_template("sogou", query) | {"error": "no results or blocked"}
        results = results[:max_results]
        results = filter_chinese_results(results)
        if results:
            return {"success": True, "provider": "sogou", "query": query, "results": results}
        return search_result_template("sogou", query) | {"error": "no results"}
    except asyncio.TimeoutError:
        return search_result_template("sogou", query) | {"error": "timeout"}
    except Exception as e:
        logger.error(f"搜狗搜索失败: {e}")
        return search_result_template("sogou", query) | {"error": str(e)[:100]}
