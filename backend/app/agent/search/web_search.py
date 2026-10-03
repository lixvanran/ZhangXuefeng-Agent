"""联网搜索 - 统一入口
v0.8.0 深度搜索 (豆包模式):
- 多个 query 变体
- 多个 provider 并行跑
- top N 抓全文
- 子问题递归 (首次搜不到, 自动拆子 query 再搜一轮)
- 全文排序去重, 给 LLM 详细带链接的整合材料

v0.10.0 修 (原实现的扇出是乘法级的, 单次搜索最坏要 3 分钟且无任何反馈):
- 1) **变体并发化**: 原来 provider 内部对 query 变体是顺序 for 循环,
       5 个变体 × 每个 ~15s = 单 provider 就 ~75s, 6 个 provider 并行仍是 ~75s 墙钟。
       改成变体也并发后, 同一 provider 内墙钟 ≈ 单个变体耗时。
- 2) **全局时间预算**: 引入 SEARCH_TIME_BUDGET_SEC, 整轮搜索有硬上限,
       预算耗尽就带着已有结果收尾, 不再无限等。
- 3) **子搜索降级**: 子问题搜索改成有条件触发 (真的一个 provider 都没成功才触发),
       且自身也受剩余预算约束, 不再叠加一整轮全 provider × 全变体。
- 4) **可观测性**: 无论成功失败都记录各源耗时/条数/错误, 写日志 + 返回给上层。
"""
import asyncio
import logging
import re
import time
from typing import Dict, List, Tuple

from app.core.config import settings
from app.agent.search.query_builder import make_queries, rewrite_query, extract_time_hint
from app.agent.search.url_fetcher import fetch_url
from app.agent.search.providers import (
    tavily_search, bing_html_search, duckduckgo_search, baidu_search,
    wikipedia_search, arxiv_search, sogou_search, so360_search,
)

logger = logging.getLogger(__name__)

# v0.10.0: 整轮搜索的硬时间预算(秒)。超时就用已有结果收尾。
SEARCH_TIME_BUDGET_SEC = 45.0
# 单个 provider 的墙钟上限
PROVIDER_TIMEOUT_SEC = 15.0
# 子问题搜索最多用掉剩余预算的这一比例
SUB_SEARCH_BUDGET_RATIO = 0.4
# v0.10.0: 相关性阈值。低于此值判定为"低可信"。
#
# 背景: 2026-10-02 实测发现, HTML 抓取类源可能"成功返回但内容与查询无关" ——
# Bing 对多 term 中文查询会退化成只匹配第一个词, 例如
#   「强基计划 报考条件」→ 返回汉字"强"的字典页面(词覆盖率 0%)
#   「强基计划」       → 正常返回招生简章(词覆盖率 100%)
# 这种情况下 provider 报 success、条数也正常, 没有任何报错信号。
# 若直接把这些当证据喂给 LLM, 结果是"答非所问但附带了看起来很权威的链接" ——
# 比搜不到更有害。所以这里加一道相关性门控。
MIN_SEARCH_RELEVANCE = 0.34

_QUERY_SPLIT = re.compile(r'[\s,，、。?？!！;；:：]+')


_QUERY_STOPWORDS = {
    # 疑问代词/副词: 不携带主题信息, 计入分母会无谓拉低覆盖率
    "怎么", "如何", "什么", "哪些", "哪个", "哪种", "多少", "几个",
    "怎么样", "是什么", "有没有", "能不能", "可不可以", "为什么", "为啥",
    # 语气/结构词
    "的", "了", "吗", "呢", "吧", "啊", "一下", "请问", "帮我", "我想",
    # 时间副词 (与时效性无关, 由 time_hint 单独处理)
    "今年", "去年", "最新", "最近", "现在", "目前",
}


def _query_terms(query: str) -> List[str]:
    """拆出查询里的实义词(去掉过短片段与常见虚词)"""
    out = []
    for t in _QUERY_SPLIT.split(query or ""):
        t = t.strip()
        if len(t) >= 2 and t not in _QUERY_STOPWORDS:
            out.append(t)
    return out


def _relevance(query: str, results: List[Dict]) -> float:
    """结果集对查询的词覆盖率 (0.0 ~ 1.0)

    只看标题 + 摘要前 300 字, 与 _score_result 的打分逻辑刻意保持独立 ——
    一个是"排谁在前", 这个是"这堆东西到底跟问题有没有关系"。
    """
    terms = _query_terms(query)
    if not terms:
        return 1.0   # 拆不出实义词, 不做判定
    if not results:
        return 0.0
    blob = " ".join(
        f"{r.get('title', '')} {r.get('content', '')[:300]}"
        for r in results
    )
    return sum(1 for t in terms if t in blob) / len(terms)


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


def _score_result(r: dict, query: str, _src: str = "") -> float:
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
    q_words = set(re.findall(r"[\w一-鿿]+", query))
    matched_in_title = 0
    if q_words:
        t_words = set(re.findall(r"[\w一-鿿]+", title))
        c_words = set(re.findall(r"[\w一-鿿]+", content[:500]))
        matched_in_title = len(q_words & t_words)
        # v0.10.0: 关键词权重从 2.0 提到 4.0, 并对"一个词都没匹配上"重罚。
        # 原设计让 gov.cn/edu.cn(+3)压过关键词匹配, 于是 Bing 用"广东省政府首页"
        # 这类答非所问的权威页面就能霸榜 —— 在相关性是主要矛盾时, 权威性不该当主导。
        score += matched_in_title * 4.0
        score += len(q_words & c_words) * 1.0
    if len(q_words) >= 2 and matched_in_title == 0:
        score -= 3.0   # 多词查询却一个词都没沾, 基本可判定为无关
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
    # v0.10.0: 搜狗/360 对中文多词查询的实测相关性明显更高, 同等条件下优先采用
    if _src in ("sogou", "so360"):
        score += 1.5
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


def _log_provider_status(stage: str, providers_status: list) -> None:
    """v0.10.0 可观测性: 把每个源的 ok/条数/耗时/错误记成一行日志

    之前只有失败路径才看得到信息, 成功时各源质量无从追溯 ——
    这正是"搜索看起来时好时坏"却查不出原因的直接原因。
    """
    parts = []
    for p in providers_status:
        mark = "OK" if p.get("ok") else "FAIL"
        err = f" err={p['error']}" if p.get("error") else ""
        parts.append(f"{p.get('name')}={mark}({p.get('count', 0)}条 {p.get('elapsed', 0)}s{err})")
    logger.info(f"[{stage}] {' '.join(parts)}")


async def _try_provider_for_all_candidates(provider_fn, candidates, max_results) -> list:
    """对所有 query 变体跑同一个 provider, 合并结果

    v0.10.0: 变体从"顺序 for"改为并发 gather。
    原来 5 个变体串行, 每个最多 15s → 单 provider 75s 墙钟;
    并发后 ≈ 单个变体耗时, 整轮墙钟降一个数量级。
    """
    async def _one(q: str, h: dict) -> list:
        try:
            result = await provider_fn(q, max_results, time_hint=h)
            if result.get("success") and result.get("results"):
                # 给每条结果标记 source query (LLM 可以看到为啥搜出来的)
                for r in result["results"]:
                    r["_source_query"] = q
                return result["results"]
            return []
        except Exception as e:
            logger.warning(f"provider {provider_fn.__name__} failed on '{q[:30]}': {e}")
            return []

    chunks = await asyncio.gather(*(_one(q, h) for q, h in candidates))
    merged = []
    for c in chunks:
        merged.extend(c)
    return merged


async def _run_one_provider(name: str, fn, candidates, max_results,
                            timeout=PROVIDER_TIMEOUT_SEC) -> Tuple[str, list, str, float]:
    """跑一个 provider, 返回 (name, results, error, elapsed_sec)

    v0.10.0: 增加耗时统计, 供可观测性使用; 超时从笼统 Exception 里单独拎出来。
    """
    t0 = time.monotonic()
    try:
        results = await asyncio.wait_for(
            _try_provider_for_all_candidates(fn, candidates, max_results),
            timeout=timeout,
        )
        return (name, results, "", round(time.monotonic() - t0, 2))
    except asyncio.TimeoutError:
        return (name, [], f"timeout after {timeout}s", round(time.monotonic() - t0, 2))
    except Exception as e:
        return (name, [], str(e)[:100], round(time.monotonic() - t0, 2))


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
    """当主 query 完全搜不到结果时, 自动生成 2-3 个子问题再搜
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
            "providers_tried": [{name, ok, count, error, elapsed}],
            "sub_searches": [子问题搜索次数],
            "fulltext_count": 抓全文成功数,
            "elapsed_sec": 整轮耗时,
            "budget_exhausted": 是否因超时提前收尾,
        }
    """
    t_start = time.monotonic()
    deadline = t_start + SEARCH_TIME_BUDGET_SEC
    candidates = make_queries(query, max_results * 2)  # 多生成变体
    time_hint = candidates[0][1] if candidates else {"now_str": "", "recency": None, "year_month": ""}

    # === 第一轮: 主搜索 (所有 provider 并行) ===
    providers_to_try: List[Tuple[str, callable]] = []
    if settings.TAVILY_API_KEY:
        providers_to_try.append(("tavily", tavily_search))
    # v0.10.0: 中文源优先。
    # 实测同一批查询的词覆盖率:
    #   强基计划 报考条件          → bing 0% / baidu 限流 / 搜狗 100% / 360 50%
    #   人工智能专业 就业前景 怎么样 → bing 0% / 360 100%
    # Bing 对多 term 中文查询会退化成只匹配第一个词(返回"汉字'强'的字典页"),
    # 所以中文源排在前面, 但仍全部并行跑(由评分层决定谁的内容更有用)。
    providers_to_try.extend([
        ("sogou", sogou_search),
        ("so360", so360_search),
        ("bing", bing_html_search),
        ("baidu", baidu_search),
        ("duckduckgo", duckduckgo_search),
        ("wikipedia", wikipedia_search),
        ("arxiv", arxiv_search),
    ])

    tasks = [
        _run_one_provider(name, fn, candidates, max_results, timeout=PROVIDER_TIMEOUT_SEC)
        for name, fn in providers_to_try
    ]
    round1_results = await asyncio.gather(*tasks, return_exceptions=True)

    all_results = []
    providers_status = []
    primary_provider = "none"
    for r in round1_results:
        if isinstance(r, Exception):
            providers_status.append({"name": "unknown", "ok": False, "count": 0,
                                     "error": str(r)[:100], "elapsed": 0.0})
            continue
        name, prov_results, err, elapsed = r
        providers_status.append({
            "name": name,
            "ok": bool(prov_results),
            "count": len(prov_results),
            "error": err,
            "elapsed": elapsed,
        })
        if prov_results:
            for x in prov_results:
                x["_provider"] = name   # 供 _score_result 做来源加权
            if primary_provider == "none":
                primary_provider = name
            all_results.extend(prov_results)

    # v0.10.0 可观测性: 成功路径也记一行, 便于事后定位"为什么这次结果这么差"
    _log_provider_status(f"round1 '{query[:40]}'", providers_status)

    # === 第二轮: 子问题搜索 ===
    # v0.10.0: 触发条件从"结果 < 3 条"收紧为"一个 provider 都没成功"。
    # 原来只要少于 3 条就叠加一整轮 (子 query × 变体 × 全 provider),
    # 在"确实搜到 1-2 条但不够多"的常见场景下白白多花 1-2 分钟, 收益微乎其微。
    sub_searches = []
    budget_exhausted = False
    ok_providers = [p for p in providers_status if p.get("ok")]
    remaining = deadline - time.monotonic()
    if not ok_providers and remaining > 5:
        sub_queries = _generate_sub_queries(query, time_hint)
        sub_deadline = min(deadline, time.monotonic() + remaining * SUB_SEARCH_BUDGET_RATIO)
        for sub_q in sub_queries[:2]:  # 最多 2 个子问题
            if time.monotonic() >= sub_deadline:
                budget_exhausted = True
                break
            sub_searches.append(sub_q)
            sub_candidates = make_queries(sub_q, max_results)
            # 每个子 query 只跑前 3 个变体, 避免子搜索再次爆炸
            sub_tasks = [
                _run_one_provider(
                    name, fn, sub_candidates[:3], max_results,
                    timeout=min(PROVIDER_TIMEOUT_SEC, max(3.0, sub_deadline - time.monotonic())))
                for name, fn in providers_to_try
            ]
            sub_results = await asyncio.gather(*sub_tasks, return_exceptions=True)
            got = 0
            for r in sub_results:
                if isinstance(r, Exception):
                    continue
                name, prov_results, err, elapsed = r
                if prov_results:
                    for x in prov_results:
                        x["_source_query"] = sub_q
                        x["_provider"] = name
                    all_results.extend(prov_results)
                    got += len(prov_results)
            logger.info(f"sub_search '{sub_q[:40]}' -> {got} 条")

    # === 去重 + 评分排序 ===
    deduped = _dedup_by_url(all_results)
    deduped.sort(key=lambda r: _score_result(r, query, r.get("_provider", "")), reverse=True)
    top_results = deduped[:max_results * 2]  # 留出抓全文失败的 buffer

    if not top_results:
        elapsed_total = round(time.monotonic() - t_start, 2)
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
            "elapsed_sec": elapsed_total,
            "budget_exhausted": budget_exhausted,
            "relevance": 0.0,
            "low_relevance": True,
        }

    # === 抓全文 (top N, 受剩余预算约束) ===
    # v0.10.0: 原来固定抓 10 个, 无视剩余时间。这里按剩余预算决定抓几个。
    remaining = deadline - time.monotonic()
    if remaining > 3:
        max_fetch = 10 if remaining > 20 else 5
        urls_to_fetch = [r.get("url", "") for r in top_results[:max_fetch]]
        fulltexts_raw = await asyncio.wait_for(
            _fetch_fulltext_batch(urls_to_fetch, max_chars=6000, max_concurrent=4),
            timeout=max(3.0, remaining),
        )
    else:
        logger.info(f"skip fulltext fetch: budget nearly exhausted ({remaining:.1f}s left)")
        fulltexts_raw = []
        budget_exhausted = True

    # 关联
    url_to_text = {ft["url"]: ft.get("text", "") for ft in fulltexts_raw if ft.get("success")}
    fulltext_count = len(url_to_text)
    # 把全文合并到结果里 (LLM 能看到)
    for r in top_results:
        url = r.get("url", "")
        if url in url_to_text and url_to_text[url]:
            r["_full_text"] = url_to_text[url]

    elapsed_total = round(time.monotonic() - t_start, 2)

    # v0.10.0 相关性门控: 抓到东西 != 搜到东西。
    # 源可能"成功返回但内容与查询无关"(见 MIN_SEARCH_RELEVANCE 注释),
    # 这里量化后交给上层决定是���用还是降级。
    final = top_results[:max_results]
    rel = _relevance(query, final)
    low_relevance = rel < MIN_SEARCH_RELEVANCE

    logger.info(
        f"web_search '{query[:40]}' {'LOW-RELEVANCE ' if low_relevance else ''}"
        f"ok: {len(final)} results ({fulltext_count} fulltext) "
        f"in {elapsed_total}s relevance={rel:.0%}"
    )
    return {
        "success": True,
        "provider": primary_provider,
        "query": query,
        "results": final,
        "candidates_tried": [c for c, _ in candidates],
        "time_hint": time_hint,
        "providers_tried": providers_status,
        "sub_searches": sub_searches,
        "fulltext_count": fulltext_count,
        "elapsed_sec": elapsed_total,
        "budget_exhausted": budget_exhausted,
        "relevance": round(rel, 3),
        "low_relevance": low_relevance,
    }
