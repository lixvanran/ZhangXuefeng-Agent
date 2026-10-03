#!/usr/bin/env python3
"""端到端真跑联网搜索 — 真实网络 + 真实 provider 抽取逻辑

## 它到底在测什么

这个仓库缺依赖时(PyPI 不可达),`httpx` / `bs4` 装不上, 后端起不来,
所以常规方式跑不了搜索。本脚本只替换**传输层绑定**:

| 组件 | 用的是真的还是替身 |
|---|---|
| `web_search.py` 调度(变体并发/时间预算/子搜索/去重/评分) | **真代码** |
| `query_builder.py`(变体生成/时效识别) | **真代码** |
| Bing / Baidu 的选择器与抽取逻辑 | **真选择器**,只是用标准库 HTMLParser 代替 bs4 |
| 中文过滤 / 垃圾结果过滤(base.py 同一套规则) | **真规则** |
| HTTP 传输 | urllib 代替 httpx(仅此一处是替身) |
| Tavily / DuckDuckGo / Wikipedia / arXiv | 无 key 或本网络不可达,跳过 |

也就是说: **除了"用什么发 HTTP 请求"和"用什么解析 HTML",其余全是仓库里的真代码。**

## 用法

    python3 scripts/real_search_test.py                    # 默认几个问题
    python3 scripts/real_search_test.py -q "你的问题"       # 问单个
    python3 scripts/real_search_test.py --full             # 显示全文摘录
"""
import argparse
import asyncio
import importlib.util
import re
import ssl
import sys
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BACKEND = None

# ===== 与 providers/base.py 完全一致的规则 =====
JUNK_DOMAINS = ["google.com/search", "google.co/search", "bing.com/search",
                "baidu.com/s", "duckduckgo.com", "yahoo.com/search"]
JUNK_TITLES = ("google", "bing", "百度一下", "百度首页", "必应")
JUNK_CONTENT_SNIPPETS = ("we would like to show you a description",
                         "the site won’t allow us", "the site won't allow us")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _has_chinese(text):
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def is_junk_result(r):
    title = (r.get("title") or "").lower()
    url = (r.get("url") or "").lower()
    content = (r.get("content") or "").lower()
    for d in JUNK_DOMAINS:
        if d in url and "search" in url:
            return True
    if title in JUNK_TITLES:
        return True
    return any(s in content for s in JUNK_CONTENT_SNIPPETS)


def filter_chinese_results(results):
    return [r for r in results
            if not is_junk_result(r)
            and (_has_chinese(r.get("title", "")) or _has_chinese(r.get("content", "")))]


def search_result_template(provider, query):
    return {"success": False, "provider": provider, "query": query,
            "results": [], "error": None}


# ===== 标准库 DOM + CSS 选择器(支持 bing.py/baidu.py 用到的语法) =====

class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children = []
        self.parent = parent
        self.text = ""

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def get_text(self, sep=" "):
        parts = [self.text] + [c.get_text(sep) for c in self.children]
        return sep.join(x for x in parts if x).strip()


class _DOM(HTMLParser):
    VOID = {"br", "img", "input", "meta", "link", "hr", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in self.VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent or self.root

    def handle_data(self, data):
        if data.strip():
            self.cur.text += data


def _select(root, selector):
    out = []
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([a-zA-Z][\w-]*)?(?:#([\w-]+))?((?:\.[\w-]+)*)", part)
        if not m:
            continue  # 复杂组合(如后代/子代)跳过, 主选择器已覆盖
        tag, _id, cls = m.group(1), m.group(2), m.group(3) or ""
        want = {c for c in cls.split(".") if c}
        for n in root.walk():
            if n.tag == "#root":
                continue
            if tag and n.tag != tag:
                continue
            if _id and n.attrs.get("id") != _id:
                continue
            if want and not want.issubset(n.classes):
                continue
            out.append(n)
    return out


def _http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.getcode(), r.read().decode("utf-8", "ignore")


def _dom(html):
    d = _DOM()
    d.feed(html)
    return d.root


# ===== 复刻 providers/bing.py =====

async def bing_html_search(query, max_results=10, time_hint=None):
    url = f"https://cn.bing.com/search?q={urllib.parse.quote_plus(query)}&setlang=zh-Hans&cc=CN&count=30"
    if time_hint:
        qft = {"day": "+filter:day", "week": "+filter:week",
               "month": "+filter:month", "year": "+filter:year"}.get(time_hint.get("recency"))
        if qft:
            url += f"&qft={urllib.parse.quote_plus(qft)}"
    loop = asyncio.get_event_loop()
    try:
        code, html = await loop.run_in_executor(None, lambda: _http_get(url))
    except Exception as e:
        return search_result_template("bing", query) | {"error": str(e)[:100]}
    if code != 200:
        return search_result_template("bing", query) | {"error": f"HTTP {code}"}

    root = _dom(html)
    containers = _select(root, "li.b_algo, li.b_algoLi, .b_algo, .b_results li, ol#b_results > li")
    if not containers:
        containers = _select(root, "li")
    results = []
    for li in containers:
        h2 = _select(li, "h2, h3, .b_title")
        if not h2:
            continue
        a = _select(h2[0], "a") or _select(li, "a.tilk, a.title")
        if not a:
            continue
        a = a[0]
        title = a.get_text(" ")
        href = a.attrs.get("href", "")
        if not href or not href.startswith("http"):
            continue
        content = ""
        for sel in (".b_caption p", ".b_snippet", ".b_algoSlug", ".b_paractl",
                    "p.b_lineclamp", ".b_caption", "p"):
            p = _select(li, sel)
            if p:
                txt = p[0].get_text(" ")
                if len(txt) > 20 and txt != title:
                    content = txt
                    break
        if not content:
            full = li.get_text(" ")
            content = (full[len(title):].strip() if full.startswith(title) else full)[:300]
        pub = ""
        for sel in (".b_factrow span", ".news_dt", "span.news_dt",
                    ".b_caption .b_attribution", "cite"):
            el = _select(li, sel)
            if el:
                pub = el[0].get_text(" ")
                break
        if title and title not in ("", "Bing", "必应") and len(title) < 200:
            results.append({"title": title, "url": href,
                            "content": content[:400],
                            "published": pub[:50] if pub else ""})
        if len(results) >= max_results:
            break
    if results:
        results = filter_chinese_results(results)
        if results:
            return {"success": True, "provider": "bing", "query": query, "results": results}
    return search_result_template("bing", query) | {"error": "no results"}


# ===== 复刻 providers/baidu.py =====
async def baidu_search(query, max_results=10, time_hint=None):
    url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    loop = asyncio.get_event_loop()
    try:
        code, html = await loop.run_in_executor(None, lambda: _http_get(url))
    except Exception as e:
        return search_result_template("baidu", query) | {"error": str(e)[:100]}
    if code != 200:
        return search_result_template("baidu", query) | {"error": f"HTTP {code}"}
    root = _dom(html)
    results = []
    for div in _select(root, "div.result, div.c-container"):
        h3 = _select(div, "h3")
        if not h3:
            continue
        a = _select(h3[0], "a")
        if not a:
            continue
        title = a[0].get_text(" ")
        href = a[0].attrs.get("href", "")
        content = ""
        for sel in ("div.c-abstract", "span.content-right_2s-H4", "div[class*=content-right]"):
            c = _select(div, sel)
            if c:
                content = c[0].get_text(" ")[:400]
                break
        if not content:
            content = div.get_text(" ")[:300]
        if title and href:
            results.append({"title": title, "url": href, "content": content})
        if len(results) >= max_results:
            break
    if results:
        results = filter_chinese_results(results)
        if results:
            return {"success": True, "provider": "baidu", "query": query, "results": results}
    return search_result_template("baidu", query) | {"error": "no results"}


async def _unavailable(name):
    return search_result_template(name, "") | {"error": "not probed in this environment"}


# ===== 装配: 加载真实的 web_search.py =====

def _load(name, rel):
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", rel)
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def _install():
    app = types.ModuleType("app"); app.__path__ = []
    agent = types.ModuleType("app.agent"); agent.__path__ = []
    core = types.ModuleType("app.core"); core.__path__ = []
    search = types.ModuleType("app.agent.search"); search.__path__ = []

    config = types.ModuleType("app.core.config")
    class _S:
        WEB_SEARCH_ENABLED = True
        TAVILY_API_KEY = ""     # 无 key, tavily 不进候选(与真机未配 key 一致)
    config.settings = _S()
    core.config = config

    qb = _load("_rt_qb", "app/agent/search/query_builder.py")

    uf = types.ModuleType("app.agent.search.url_fetcher")
    async def fetch_url(url, max_chars=6000):
        loop = asyncio.get_event_loop()
        try:
            code, html = await loop.run_in_executor(
                None, lambda: _http_get(url, timeout=8))
        except Exception as e:
            return {"success": False, "url": url, "error": str(e)[:80]}
        root = _dom(html)
        for n in root.walk():
            if n.tag in ("script", "style", "nav", "footer", "header", "aside", "form", "iframe"):
                n.text = ""
        main = _select(root, "article, main, .article-content, .content, #content")
        node = main[0] if main else (_select(root, "body") or [root])[0]
        text = node.get_text("\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        return {"success": True, "url": url, "text": text, "truncated": truncated}
    uf.fetch_url = fetch_url
    search.url_fetcher = uf

    prov = types.ModuleType("app.agent.search.providers")

    def _load_provider(modname, rel, fname):
        import os as _os, importlib.util as _iu
        base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "backend", rel)
        sp = _iu.spec_from_file_location(modname, base)
        m = _iu.module_from_spec(sp); sys.modules[modname] = m
        sp.loader.exec_module(m)
        return getattr(m, fname)

    prov.tavily_search = lambda *a, **k: _unavailable("tavily")
    prov.bing_html_search = bing_html_search
    prov.duckduckgo_search = lambda *a, **k: _unavailable("duckduckgo")
    prov.baidu_search = baidu_search
    # 中文源: 复用真实现(它们只用标准库, 无需 httpx/bs4)
    def _load_provider(modname, rel, fname):
        import os as _os
        base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "backend", rel)
        import importlib.util as _iu
        sp = _iu.spec_from_file_location(modname, base)
        m = _iu.module_from_spec(sp); sys.modules[modname] = m
        sp.loader.exec_module(m)
        return getattr(m, fname)
    prov.wikipedia_search = lambda *a, **k: _unavailable("wikipedia")
    prov.arxiv_search = lambda *a, **k: _unavailable("arxiv")
    search.providers = prov

    for m, mod in [("app", app), ("app.agent", agent), ("app.core", core),
                   ("app.core.config", config), ("app.agent.search", search),
                   ("app.agent.search.query_builder", qb),
                   ("app.agent.search.url_fetcher", uf),
                   ("app.agent.search.providers", prov)]:
        sys.modules[m] = mod

    # providers 桩补成包, 并提供真实的 base 子模块,
    # 这样 sogou/so360 的 `from ...providers.base import ...` 才能解析
    prov.__path__ = []
    base_mod = _load("_rt_base", "app/agent/search/providers/base.py")
    sys.modules["app.agent.search.providers.base"] = base_mod
    prov.base = base_mod
    prov.search_result_template = base_mod.search_result_template
    prov.filter_chinese_results = base_mod.filter_chinese_results

    # 桩注册完毕后再加载真实中文源(它们的 import 依赖 app.* 已在 sys.modules)
    prov.sogou_search = _load_provider("_p_sogou", "app/agent/search/providers/sogou.py", "sogou_search")
    prov.so360_search = _load_provider("_p_so360", "app/agent/search/providers/so360.py", "so360_search")

    ws = _load("_rt_ws", "app/agent/search/web_search.py")
    sys.modules["app.agent.search"].web_search = ws
    return ws


DEFAULT_QUESTIONS = [
    "广东 2025 高考一本线 多少分",
    "人工智能专业 就业前景 怎么样",
    "计算机和电气工程 哪个更好",
    "强基计划 报考条件",
]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-q", "--query", action="append", help="可重复")
    ap.add_argument("--full", action="store_true", help="显示全文摘录")
    ap.add_argument("--n", type=int, default=5, help="每个问题返回几条")
    args = ap.parse_args()

    questions = args.query or DEFAULT_QUESTIONS
    ws = _install()

    print("=" * 74)
    print("联网搜索 端到端真跑")
    print("  调度/变体/去重/评分 = 仓库真代码")
    print("  Bing+Baidu 抽取      = 真选择器 (标准库 HTMLParser 代替 bs4)")
    print("  网络                 = 真实请求")
    print("  未测                 = Tavily(无key) / DDGS / Wikipedia(网络不可达) / arXiv")
    print("=" * 74)

    all_ok = True
    for q in questions:
        t0 = time.monotonic()
        res = await ws.web_search(q, max_results=args.n)
        wall = round(time.monotonic() - t0, 2)

        print(f"\n{'─' * 74}")
        print(f"❓ {q}")
        print(f"   成功={res.get('success')} | 主源={res.get('provider')} | "
              f"耗时={res.get('elapsed_sec')}s (墙钟 {wall}s) | "
              f"结果={len(res.get('results', []))} 条 | 全文={res.get('fulltext_count')} 条")
        print(f"   变体: {res.get('candidates_tried')}")
        prov_bits = []
        for p in res.get("providers_tried", []):
            mark = "OK " if p["ok"] else "-- "
            prov_bits.append(f"{mark}{p['name']}:{p['count']}({p.get('elapsed')}s)")
        print(f"   各源: {'  '.join(prov_bits)}")
        if res.get("sub_searches"):
            print(f"   子搜索: {res['sub_searches']}")
        if res.get("budget_exhausted"):
            print("   ⚠️ 触发时间预算提前收尾")
        rel = res.get("relevance")
        if rel is not None:
            gate = "🚫 低可信(已拦)" if res.get("low_relevance") else "✅ 通过"
            print(f"   相关性: {rel:.0%} {gate}")

        if not res.get("success"):
            all_ok = False
            print("   ❌ 没有搜到任何东西")
            for p in res.get("providers_tried", []):
                if p.get("error"):
                    print(f"      {p['name']}: {p['error']}")
            continue

        for i, r in enumerate(res["results"], 1):
            print(f"\n   [{i}] {r.get('title','')[:60]}")
            print(f"       🔗 {r.get('url','')[:100]}")
            if r.get("published"):
                print(f"       📅 {r['published']}")
            c = r.get("content", "")
            if c:
                print(f"       📄 {c[:140]}{'…' if len(c) > 140 else ''}")
            if args.full and r.get("_full_text"):
                ft = r["_full_text"]
                print(f"       ── 全文 {len(ft)} 字 ──")
                print("       " + ft[:600].replace("\n", "\n       ") + ("…" if len(ft) > 600 else ""))

    print(f"\n{'=' * 74}")
    print("全部问题都有结果" if all_ok else "有问题没搜到结果")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
