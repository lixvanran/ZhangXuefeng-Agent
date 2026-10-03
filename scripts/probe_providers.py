#!/usr/bin/env python3
"""联网搜索「真实可用性」探针 — 直连外网, 跑 provider 的真实抽取逻辑

## 为什么需要这个

仓库里的搜索测试全部是**桩 provider**, 只能证明调度层(并发/预算/超时/降级)
是对的, **证明不了任何一个 provider 真的能抓到东西**。

而 provider 里风险最高的是 bing.py / baidu.py 这类 **HTML 抓取**:
它们靠 CSS 选择器解析页面, 站点一改版就静默返回 0 条 ——
不报错、不告警, 用户只会觉得"张老师今天变傻了"。

本脚本用标准库直连真实搜索页, 复刻 provider 里那套选择器链,
报告: 能否连通 / 选择器是否仍命中 / 抽出几条 / 被垃圾过滤掉几条。

不依赖 fastapi/httpx/bs4, 所以在 PyPI 不可达的环境里也能跑。

## 用法

    python3 scripts/probe_providers.py                # 探全部
    python3 scripts/probe_providers.py --provider bing
    python3 scripts/probe_providers.py --json         # 便于接入 CI 对比

## 注意

会向 cn.bing.com / www.baidu.com 发起真实请求, 单次约 1-2 秒。
不要高频跑 —— 既是礼貌, 也避免被限流。
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0")

# 与 backend/app/agent/search/providers/base.py 的 JUNK_DOMAINS / JUNK_TITLES 保持一致
JUNK_DOMAINS = [
    "google.com/search", "google.co/search",
    "bing.com/search", "baidu.com/s",
    "duckduckgo.com", "yahoo.com/search",
]
JUNK_TITLES = ("google", "bing", "百度一下", "百度首页", "必应")


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

    def get_text(self, sep=" ", strip=True):
        out = [self.text]
        for c in self.children:
            out.append(c.get_text(sep, strip))
        s = sep.join(x for x in out if x)
        return s.strip() if strip else s


class _DOM(HTMLParser):
    """极简 DOM, 够跑 provider 里的选择器链"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = _Node(tag, attrs, self.cur)
        self.cur.children.append(n)
        if tag not in ("br", "img", "input", "meta", "link", "hr"):
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
    """支持 'li.b_algo' / 'a.tilk, a.title' / 'h2, h3, .b_title' 这类简单选择器"""
    out = []
    for part in selector.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([a-zA-Z][\w-]*)?(?:#([\w-]+))?((?:\.[\w-]+)*)", part)
        if not m:
            continue
        tag, _id, classes = m.group(1), m.group(2), m.group(3) or ""
        want = set(c for c in classes.split(".") if c)
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


def _has_chinese(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))


def is_junk(r):
    title = (r.get("title") or "").lower()
    url = (r.get("url") or "").lower()
    content = (r.get("content") or "").lower()
    for d in JUNK_DOMAINS:
        if d in url and "search" in url:
            return True
    if title in JUNK_TITLES:
        return True
    return any(s in content for s in (
        "we would like to show you a description",
        "the site won’t allow us", "the site won't allow us"))


def filter_chinese(results):
    return [r for r in results
            if not is_junk(r) and (_has_chinese(r.get("title")) or _has_chinese(r.get("content")))]


def _fetch(url, timeout=15):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.getcode(), resp.read().decode("utf-8", "ignore")


# ===== 相关性评估 =====

def _terms(q):
    return [t for t in re.split(r"[\s,，、]+", q) if len(t) >= 2]


def relevance(query, titles):
    """结果标题覆盖了查询里多少个实义词 —— 衡量"搜到了但没用"的关键指标"""
    terms = _terms(query)
    if not terms:
        return 0.0
    blob = " ".join(titles)
    return sum(1 for t in terms if t in blob) / len(terms)


def classify(source, res, query):
    """把探针结果翻译成一句可执行的结论"""
    if not res.get("reachable"):
        return "不可达", "该源连不上"
    if res.get("raw_extracted", 0) == 0:
        return "失效", "选择器 0 命中(站点改版或被反爬拦截)"
    if res.get("error") == "ratelimited":
        return "限流", "返回验证页, 该 IP 被临时封禁(HTML 抓取的固有风险)"
    if not res.get("after_chinese_filter"):
        return "失效", "抽到结果但全被中文过滤清空"
    if res.get("rel", 0) < 0.34:
        return "低质", (f"关键词覆盖率仅 {res['rel']:.0%} — "
                       f"疑似只匹配了查询的第一个词, 多 term 查询基本不可用")
    return "可用", f"关键词覆盖率 {res['rel']:.0%}"


# ===== 复刻 bing.py 的抽取逻辑 =====

def probe_bing(query="广东 2025 高考一本线", max_results=10):
    url = ("https://cn.bing.com/search?q=" + urllib.parse.quote_plus(query)
           + "&setlang=zh-Hans&cc=CN&count=30")
    t0 = time.monotonic()
    code, html = _fetch(url)
    elapsed = round(time.monotonic() - t0, 2)

    dom = _DOM()
    dom.feed(html)
    root = dom.root

    selector_stats = {}
    containers = _select(root, "li.b_algo, li.b_algoLi, .b_algo, .b_results li, ol#b_results > li")
    selector_stats["container(li.b_algo,…)"] = len(containers)
    if not containers:
        containers = _select(root, "li")
        selector_stats["fallback(li)"] = len(containers)

    results = []
    for li in containers:
        h2 = _select(li, "h2, h3, .b_title")
        if not h2:
            continue
        a = _select(h2[0], "a") or _select(li, "a.tilk, a.title")
        if not a:
            continue
        a = a[0]
        title = a.get_text(" ", True)
        href = a.attrs.get("href", "")
        if not href.startswith("http"):
            continue
        content = ""
        for sel in (".b_caption p", ".b_snippet", ".b_algoSlug", ".b_paractl",
                    "p.b_lineclamp", ".b_caption", "p"):
            p = _select(li, sel)
            if p:
                txt = p[0].get_text(" ", True)
                if len(txt) > 20 and txt != title:
                    content = txt
                    break
        if not content:
            full = li.get_text(" ", True)
            content = (full[len(title):].strip() if full.startswith(title) else full)[:300]
        pub = ""
        for sel in (".b_factrow span", ".news_dt", "span.news_dt",
                    ".b_caption .b_attribution", "cite"):
            el = _select(li, sel)
            if el:
                pub = el[0].get_text(" ", True)
                break
        if title and title not in ("", "Bing", "必应") and len(title) < 200:
            results.append({"title": title, "url": href,
                            "content": content[:400], "published": pub[:50] if pub else ""})
        if len(results) >= max_results:
            break

    kept = filter_chinese(results)
    if len(html) < 5000:
        return {"provider": "bing", "reachable": True, "http": code,
                "elapsed": elapsed, "selector_hits": {"-": 0},
                "raw_extracted": 0, "after_chinese_filter": 0,
                "error": "ratelimited", "rel": 0.0, "titles": []}
    return {
        "provider": "bing", "reachable": code == 200, "http": code,
        "rel": relevance(query, [r["title"] for r in kept]),
        "titles": [r["title"] for r in kept],
        "elapsed": elapsed, "selector_hits": selector_stats,
        "raw_extracted": len(results), "after_chinese_filter": len(kept),
        "sample": [{"title": r["title"][:40], "url": r["url"][:60]} for r in kept[:3]],
    }


# ===== 复刻 baidu.py 的抽取逻辑 =====

def probe_baidu(query="广东 2025 高考一本线", max_results=10):
    url = "https://www.baidu.com/s?wd=" + urllib.parse.quote(query)
    t0 = time.monotonic()
    try:
        code, html = _fetch(url)
    except Exception as e:
        return {"provider": "baidu", "reachable": False,
                "error": f"{type(e).__name__}: {e}",
                "elapsed": round(time.monotonic() - t0, 2)}
    elapsed = round(time.monotonic() - t0, 2)

    dom = _DOM()
    dom.feed(html)
    root = dom.root

    hits = len(_select(root, "div.result, div.c-container, div[class*=result]"))
    results = []
    for div in _select(root, "div.result, div.c-container"):
        h3 = _select(div, "h3")
        if not h3:
            continue
        a = _select(h3[0], "a")
        if not a:
            continue
        title = a[0].get_text(" ", True)
        href = a[0].attrs.get("href", "")
        content = ""
        for sel in ("div.c-abstract", "span.content-right_2s-H4", "div[class*=content-right]"):
            c = _select(div, sel)
            if c:
                content = c[0].get_text(" ", True)[:400]
                break
        if not content:
            content = div.get_text(" ", True)[:300]
        if title and href:
            results.append({"title": title, "url": href, "content": content})
        if len(results) >= max_results:
            break

    kept = filter_chinese(results)
    return {
        "provider": "baidu", "reachable": code == 200, "http": code,
        "rel": relevance(query, [r["title"] for r in kept]),
        "titles": [r["title"] for r in kept],
        "elapsed": elapsed, "selector_hits": {"container(div.result,…)": hits},
        "raw_extracted": len(results), "after_chinese_filter": len(kept),
        "sample": [{"title": r["title"][:40], "url": r["url"][:60]} for r in kept[:3]],
    }


PROBES = {"bing": probe_bing, "baidu": probe_baidu}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=sorted(PROBES), help="只探某一个")
    ap.add_argument("--query", default="广东 2025 高考一本线")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = [args.provider] if args.provider else sorted(PROBES)
    report = []
    for name in targets:
        res = PROBES[name](args.query)
        report.append(res)
        if not args.json:
            print(f"\n{'=' * 62}")
            print(f"[{name}]  连通={'✓' if res.get('reachable') else '✗'}  "
                  f"耗时={res.get('elapsed')}s")
            if res.get("error"):
                print(f"  错误: {res['error']}")
                continue
            for k, v in res["selector_hits"].items():
                print(f"  选择器 {k:<32} 命中 {v}{'   <-- 0, 该源已失效' if not v else ''}")
            print(f"  原始抽取 {res['raw_extracted']} 条 → "
                  f"中文过滤后 {res['after_chinese_filter']} 条")
            if res.get("rel") is not None:
                state, why = classify(res["provider"], res, args.query)
                print(f"  判定: 【{state}】 {why}")
            for s in res["sample"]:
                print(f"    · {s['title']}")
                print(f"      {s['url']}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 62}")
        healthy = [r for r in report
                   if r.get("reachable") and r["after_chinese_filter"] > 0]
        dead = [r for r in report if r not in healthy]
        print(f"可用: {', '.join(r['provider'] for r in healthy) or '无'}")
        print(f"失效: {', '.join(r['provider'] for r in dead) or '无'}")
    return 0 if all(r.get("reachable") for r in report) else 1


if __name__ == "__main__":
    sys.exit(main())
