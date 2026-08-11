"""URL 抓全文 - 给搜索结果注入完整文章内容到 LLM context
"""
import logging
import re as _re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


async def fetch_url(url: str, max_chars: int = 3500) -> str:
    """抓取 URL 全文, 清理后返回
    - 剥 script/style/nav/footer
    - 压缩空白
    - 截断到 max_chars
    """
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        # 移除无意义标签
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        # 压缩空白
        text = _re.sub(r"\n\s*\n", "\n\n", text)
        text = _re.sub(r"[ \t]+", " ", text)
        return text[:max_chars].strip()
    except Exception as e:
        logger.debug(f"fetch_url({url}) failed: {e}")
        return ""


async def fetch_top_n(results: list, n: int = 3, max_chars: int = 3500) -> list:
    """批量抓 top N 搜索结果, 返回 [{"title", "url", "content", "full_text"}, ...]"""
    import asyncio
    top = results[:n]
    urls = [r.get("url", "") for r in top]
    if not urls:
        return []
    full_texts = await asyncio.gather(*(fetch_url(u, max_chars) for u in urls))
    for r, ft in zip(top, full_texts):
        r["full_text"] = ft
    return top
