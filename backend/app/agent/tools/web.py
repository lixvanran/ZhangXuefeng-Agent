"""联网工具 - search_web / fetch_url
v0.8.0 深度搜索:
- 拿全 6 个 provider 的合并结果
- top 10 抓全文 (web_search 已经抓了, 这里直接用)
- LLM 拿到的是 "标题 + 摘要 + 全文片段" 三层信息
- 子问题搜索
"""
import logging
from datetime import datetime
from typing import Dict

from app.core.config import settings
from app.agent.search import web_search
from app.agent.search.url_fetcher import fetch_url as _fetch_url

logger = logging.getLogger(__name__)


async def search_web(query: str, max_results: int = 8) -> Dict:
    """联网搜索 - 深度模式
    v0.8.0: max_results 默认 8 (不是 5), LLM 拿到更多材料
    """
    if not settings.WEB_SEARCH_ENABLED:
        return {
            "success": False,
            "disabled": True,
            "message": "Web search is currently DISABLED in settings. Answer with your existing knowledge and recommend authoritative news sources.",
            "results": [],
        }
    # 让 web_search 抓全文 (10 个 URL)
    result = await web_search(query, max_results)
    if result.get("success") and result.get("results"):
        # web_search 已经抓了全文, 我们整理成 fulltexts 列表
        fulltexts = []
        for r in result["results"]:
            url = r.get("url", "")
            if r.get("_full_text"):
                fulltexts.append({
                    "url": url,
                    "title": r.get("title", ""),
                    "text": r["_full_text"],
                })
        result["fulltexts"] = fulltexts
        result["formatted"] = _format_search_result(query, result, fulltexts)
    else:
        time_hint = result.get("time_hint", {}) or {}
        now_str = time_hint.get("now_str", datetime.now().strftime("%Y-%m-%d"))
        providers_status = result.get("providers_tried", [])
        provider_lines = []
        for ps in providers_status:
            ok = "✅" if ps.get("ok") else "❌"
            err = f" - {ps.get('error','')}" if ps.get("error") else ""
            provider_lines.append(f"  - {ok} {ps.get('name')}: {ps.get('count')} 条{err}")
        sub_searches = result.get("sub_searches", [])
        sub_line = f"\n子问题搜索: {', '.join(sub_searches)}" if sub_searches else ""
        result["formatted"] = (
            f"## 搜索结果 (查询: {query}, 检索时间: {now_str})\n\n"
            f"⚠️ 主搜索 + 子搜索都失败: {result.get('error', '未知')}\n\n"
            f"### 各源状态:\n" + "\n".join(provider_lines) + sub_line + "\n\n"
            f"请用你的已有知识回答，并建议用户去权威源（新华社、人民日报、央视新闻、Wikipedia）获取最新信息。"
        )
    return result


def _format_search_result(query: str, result: Dict, fulltexts: list) -> str:
    """拼 LLM 友好的搜索结果文本 — v0.8.0 详细版
    包含: 列表标题 + 摘要 + 全文, 让 LLM 能整合成"豆包式"深度答案
    """
    time_hint = result.get("time_hint", {}) or {}
    now_str = time_hint.get("now_str", datetime.now().strftime("%Y-%m-%d"))
    recency_zh = {
        "day": "今天内", "week": "本周内", "month": "本月内", "year": "今年内",
    }.get(time_hint.get("recency"), "近期")
    providers_status = result.get("providers_tried", [])
    fulltext_count = result.get("fulltext_count", 0)
    sub_searches = result.get("sub_searches", [])

    lines = [
        f"# 🔍 联网搜索结果 (查询: {query}, 检索时间: {now_str})",
        f"",
        f"## 📊 搜索概览",
        f"- 来源数: {len(providers_status)} (主搜索 {'+'.join([p['name'] for p in providers_status if p.get('ok')]) or '全失败'})",
        f"- 返回: {len(result['results'])} 条结果",
        f"- 抓全文: {fulltext_count} 条",
        f"- 子问题: {len(sub_searches)} 次" + (f" ({', '.join(sub_searches)})" if sub_searches else ""),
        f"- 用户期望时效性: {recency_zh}",
        f"",
        "## 📋 搜索结果 (含摘要)",
        "",
    ]

    # 列表
    for i, r in enumerate(result["results"][:max(12, 8)], 1):
        lines.append(f"### [{i}] {r.get('title', '')}")
        meta_parts = []
        if r.get("published"):
            meta_parts.append(f"📅 {r.get('published')}")
        if r.get("url"):
            meta_parts.append(f"🔗 {r.get('url')}")
        if r.get("language"):
            meta_parts.append(f"🌐 {r.get('language')}")
        if r.get("authors"):
            meta_parts.append(f"✍️ {r.get('authors')}")
        if meta_parts:
            lines.append("  " + " | ".join(meta_parts))
        if r.get("content"):
            content = r["content"]
            if len(content) > 800:
                content = content[:800] + "..."
            lines.append(f"  摘要: {content}")
        lines.append("")

    # 全文 (分块展示, 让 LLM 能引用)
    if fulltexts:
        lines.append("---")
        lines.append(f"## 📄 全文摘录 ({len(fulltexts)} 条, 用于深度整合)")
        lines.append("")
        for i, ft in enumerate(fulltexts, 1):
            lines.append(f"### 📄 全文 [{i}] {ft['title']}")
            lines.append(f"URL: {ft['url']}")
            text = ft['text']
            if len(text) > 4000:
                text = text[:4000] + "\n\n[...截断, 原文更长...]"
            lines.append("```")
            lines.append(text)
            lines.append("```")
            lines.append("")

    # 时效性提醒
    if time_hint.get("recency") in ("day", "week", "month"):
        lines.append(f"## ⚠️ 时效性提醒")
        lines.append(f"用户期望的是{recency_zh}的信息，但搜索引擎返回的结果可能不全符合时效。")
        lines.append(f"**请按以下优先级整合:**")
        lines.append(f"1. 全文里明确出现\"{now_str}\" 或最近日期的 → 最可信")
        lines.append(f"2. 全文里出现具体数字 (如分数线) 但没明确日期的 → 注明 '来源未注日期'")
        lines.append(f"3. 只有摘要的 → 列出供用户参考, 让他去原链接确认")
        lines.append(f"4. 实在没最新信息 → 诚实告诉用户, 给他权威源链接")
        lines.append("")
    lines.append("## 🎯 你的任务")
    lines.append(f"基于上面的搜索结果,**像豆包一样**给用户一个整合、有条理、有具体数字、有来源链接的答案。")
    lines.append(f"不要只复述摘要, 要把多个来源的信息合并, 找出共同点/矛盾点, 给出你的判断。")
    return "\n".join(lines)


async def fetch_url(url: str, max_chars: int = 6000) -> Dict:
    """抓 URL 全文 - 给 search_web 后续用 / 工具直接调用
    v0.8.0: 默认 6000 字符
    """
    import re as _re
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return {"success": False, "url": url, "error": f"HTTP {resp.status_code}"}
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
            tag.decompose()
        root = soup.select_one("article, main, .article-content, .content, #content")
        if not root:
            root = soup.body or soup
        text = root.get_text("\n", strip=True)
        text = _re.sub(r"\n{3,}", "\n\n", text)
        text = _re.sub(r"[ \t]+", " ", text)
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + f"\n\n[...截断，原文 {len(text)} 字符...]"
        return {"success": True, "url": url, "text": text, "truncated": truncated}
    except Exception as e:
        logger.error(f"fetch_url error for {url}: {e}")
        return {"success": False, "url": url, "error": str(e)}
