"""联网搜索 - 统一入口
v0.8.0 深度搜索 (豆包模式):
- 8+ 个 query 变体
- 6 个 provider 并行跑
- top 10 抓全文 (不是 3 个)
- 子问题递归 (首次搜不到, 自动拆子 query 再搜一轮)
- 全文排序去重, 给 LLM 详细带链接的整合材料
"""
import asyncio
import logging
import re
from typing import Dict, List, Tuple

from app.core.config import settings
from app.agent.search.query_builder import make_queries, rewrite_query, extract_time_hint
from app.agent.search.url_fetcher import fetch_url
from app.agent.search.providers import (
    tavily_search, bing_html_search, duckduckgo_search, baidu_search,
    wikipedia_search, arxiv_search,
)

logger = logging.getLogger(__name__)


# ===== 工具函数 =====

def _dedup_by_url(results: list) -> list:
    """按 URL 去重, 保留先出现的"""
    seen = set()
    out = []
    for r in results:
        u = (r.get("url") or "").rstrip("/").split("?")[0]
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(r)
    return out


def _score_result(r: dict, query: str) -> float:
    """给一条结果打分, 用于排序 (高分在前)
    - 标题含 query 关键词: +5
    - 内容含 query 关键词: +2
    - 来源权威: 知乎+1, 微信公众号+0.5, 百家号+0.2, 其他+0.5
    - 短 URL (不是搜索结果页): +1
    - 有发布时间: +1
    """
    score = 0.0
    title = r.get("title", "")
    content = r.get("content", "")
    url = r.get("url", "")
    # query 关键词匹配
    q_words = set(re.findall(r"[\w\u4e00-\u9fff]+", query))
    if q_words:
        t_words = set(re.findall(r"[\w\u4e00-\u9fff]+", title))
        c_words = set(re.findall(r"[\w\u4e00-\u9fff]+", content[:500]))
        score += len(q_words & t_words) * 2.0
        score += len(q_words & c_words) * 0.5
    # 来源权威 (适度)
    if "wikipedia.org" in url:
        score += 3
    elif "arxiv.org" in url:
        score += 2
    elif "zhihu.com" in url:
        score += 1.5
    elif "weixin" in url or "mp.weixin" in url:
        score += 1
    elif "baijiahao" in url or "百家号" in title:
        score -= 0.5
    elif "gov.cn" in url or "edu.cn" in url:
        score += 3
    # 有发布时间加分
    if r.get("published"):
        score += 1
    # 短 URL (不是搜索结果页)
    if len(url) < 100:
        score += 0.5
    # 内容长度
    if len(content) > 200:
        score += 1
    return score


async def _try_provider_for_all_candidates(provider_fn, candidates, max_results) -> list:
    """对所有 query 变体跑同一个 provider, 合并结果"""
    merged = []
    for q, h in candidates:
        try:
            result = await provider_fn(q, max_results, time_hint=h)
            if result.get("success") and result.get("results"):
                # 给每条结果标记 source query (LLM 可以看到为啥搜出来的)
                for r in result["results"]:
                    r["_source_query"] = q
                merged.extend(result["results"])
        except Exception as e:
            logger.warning(f"provider {provider_fn.__name__} failed on '{q[:30]}': {e}")
    return merged


async def _run_one_provider(name: str, fn, candidates, max_results, timeout=12.0) -> Tuple[str, list, str]:
    """跑一个 provider, 返回 (name, results, error)"""
    try:
        results = await asyncio.wait_for(
            _try_provider_for_all_candidates(fn, candidates, max_results),
            timeout=timeout,
        )
        return (name, results, "")
    except Exception as e:
        return (name, [], str(e)[:100])


async def _fetch_fulltext_batch(urls: List[str], max_chars: int = 6000, max_concurrent: int = 5) -> List[Dict]:
    """并发抓多个 URL 全文
    v0.8.0: max_chars 从 3500 提到 6000, max_concurrent=5 (不堵死)
    """
    sem = asyncio.Semaphore(max_concurrent)

    async def _fetch_one(url: str) -> Dict:
        async with sem:
            try:
                r = await _fetch_url_direct(url, max_chars)
                return {"url": url, "text": r.get("text", "") if r.get("success") else "", "success": r.get("success", False)}
            except Exception as e:
                return {"url": url, "text": "", "success": False, "error": str(e)[:80]}

    tasks = [_fetch_one(u) for u in urls if u and u.startswith("http")]
    return await asyncio.gather(*tasks)


async def _fetch_url_direct(url: str, max_chars: int = 6000) -> Dict:
    """直接抓 URL, 复用 url_fetcher 逻辑"""
    try:
        result = await fetch_url(url, max_chars=max_chars)
        return result
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)[:80]}


# ===== 子问题拆分 =====

def _generate_sub_queries(query: str, time_hint: dict) -> List[str]:
    """当主 query 搜不到结果时, 自动生成 2-3 个子问题再搜
    比如 "武汉 2026 中考普高线" → ["武汉 2026 中考分数线", "武汉教育局 2026 录取线", "湖北武汉中考 普高"]
    """
    subs = []
    q = query.strip()
    # 提取年份 (2024/2025/2026)
    year_match = re.search(r'20\d{2}', q)
    year = year_match.group(0) if year_match else time_hint.get("year_month", "")
    # 提取省份/城市
    from app.agent.search.query_builder import PROVINCES
    prov_match = re.search(PROVINCES, q)
    prov = prov_match.group(0) if prov_match else ""
    # 提取主题
    topic = re.sub(r'20\d{2}|' + PROVINCES + r'|今年|去年|最新|最近|分数|线|多少', '', q).strip()
    # 生成 3 个变体
    if prov and topic:
        subs.append(f"{prov} {year} {topic}")
        subs.append(f"{prov} {year} 录取线")
        subs.append(f"{prov} {year} {topic} 公告")
    elif topic:
        subs.append(f"{topic} {year}")
        subs.append(f"{year} {topic} 官方")
    return subs[:3]


# ===== 主入口 =====

async def web_search(query: str, max_results: int = 8) -> Dict:
    """统一入口, v0.8.0 深度搜索
    Args:
        query: 用户问题
        max_results: 目标返回条数
    Returns:
        {
            "success": True/False,
            "provider": "wikipedia" | ... | "none",
            "query": 原 query,
            "results": [排序后的 top max_results 条],
            "candidates_tried": [变体 query 列表],
            "time_hint": {recency, now_str, year_month},
            "providers_tried": [(name, ok, count, error), ...],
            "sub_searches": [子问题搜索次数],
            "fulltext_count": 抓全文成功数,
        }
    """
    candidates = make_queries(query, max_results * 2)  # 多生成变体
    time_hint = candidates[0][1] if candidates else {"now_str": "", "recency": None, "year_month": ""}

    # === 第一轮: 主搜索 (6 provider 并行) ===
    providers_to_try: List[Tuple[str, callable]] = []
    if settings.TAVILY_API_KEY:
        providers_to_try.append(("tavily", tavily_search))
    providers_to_try.extend([
        ("bing", bing_html_search),
        ("duckduckgo", duckduckgo_search),
        ("baidu", baidu_search),
        ("wikipedia", wikipedia_search),
        ("arxiv", arxiv_search),
    ])

    tasks = [
        _run_one_provider(name, fn, candidates, max_results, timeout=15.0)
        for name, fn in providers_to_try
    ]
    round1_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    providers_status = []
    primary_provider = "none"
    for r in round1_results:
        if isinstance(r, Exception):
            providers_status.append({"name": "unknown", "ok": False, "count": 0, "error": str(r)[:100]})
            continue
        name, prov_results, err = r
        providers_status.append({
            "name": name,
            "ok": bool(prov_results),
            "count": len(prov_results),
            "error": err,
        })
        if prov_results:
            if primary_provider == "none":
                primary_provider = name
            all_results.extend(prov_results)

    # === 第二轮: 子问题搜索 (主搜没结果时) ===
    sub_searches = []
    if len(all_results) < 3:
        sub_queries = _generate_sub_queries(query, time_hint)
        for sub_q in sub_queries[:2]:  # 最多 2 个子问题
            sub_searches.append(sub_q)
            sub_candidates = make_queries(sub_q, max_results)
            sub_tasks = [
                _run_one_provider(name, fn, sub_candidates, max_results, timeout=10.0)
                for name, fn in providers_to_try
            ]
            sub_results = await asyncio.gather(*sub_tasks, return_exceptions=True)
            for r in sub_results:
                if isinstance(r, Exception):
                    continue
                name, prov_results, err = r
                if prov_results:
                    for x in prov_results:
                        x["_source_query"] = sub_q
                    all_results.extend(prov_results)

    # === 去重 + 评分排序 ===
    deduped = _dedup_by_url(all_results)
    deduped.sort(key=lambda r: _score_result(r, query), reverse=True)
    top_results = deduped[:max_results * 2]  # 留出抓全文失败的 buffer

    if not top_results:
        return {
            "success": False,
            "provider": "none",
            "query": query,
            "results": [],
            "candidates_tried": [c for c, _ in candidates],
            "time_hint": time_hint,
            "error": "所有搜索源都不可用",
            "providers_tried": providers_status,
            "sub_searches": sub_searches,
            "fulltext_count": 0,
        }

    # === 抓全文 (top 10) ===
    urls_to_fetch = [r.get("url", "") for r in top_results[:10]]
    fulltexts_raw = await _fetch_fulltext_batch(urls_to_fetch, max_chars=6000, max_concurrent=4)
    # 关联
    url_to_text = {ft["url"]: ft.get("text", "") for ft in fulltexts_raw if ft.get("success")}
    fulltext_count = len(url_to_text)
    # 把全文合并到结果里 (LLM 能看到)
    for r in top_results:
        url = r.get("url", "")
        if url in url_to_text and url_to_text[url]:
            r["_full_text"] = url_to_text[url]

    return {
        "success": True,
        "provider": primary_provider,
        "query": query,
        "results": top_results[:max_results],
        "candidates_tried": [c for c, _ in candidates],
        "time_hint": time_hint,
        "providers_tried": providers_status,
        "sub_searches": sub_searches,
        "fulltext_count": fulltext_count,
    }
