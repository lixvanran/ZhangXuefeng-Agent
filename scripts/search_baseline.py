#!/usr/bin/env python3
"""搜索源健康度基线 — 给"搜索时好时坏"一个可量化的参照

## 为什么需要这个

修完 v0.10.0 的调度层之后,搜索不再卡死、也修好了 Tavily,
但"质量到底怎么样"仍然只能靠肉眼看结果。一旦某天搜索变差,
没有基线就无从判断是**代码改坏了**还是**外部源本身波动**。

本脚本对一组固定的高考相关 query 逐个跑真实搜索,输出:

- 每个 provider 的成功率 / 平均耗时 / 返回条数
- 整体成功率、p50/p95 耗时
- 与上次基线(JSON 文件)的差异

## 两种运行模式

**离线自检(默认, 不需要任何网络/依赖)**
    python3 scripts/search_baseline.py --self-test

用桩 provider 跑一遍调度层,验证脚本自身能跑通。CI / 裸环境用这个。

**真实基线(需要依赖与网络)**
    python3 scripts/search_baseline.py --run --save baseline.json

在有 `pip install -r backend/requirements.txt` 的环境里跑。

## 注意

`--run` 会**真实发起网络请求**。脚本自身不消耗 LLM token,
但被搜的站点可能有限流,建议不要高频重复跑。
"""
import argparse
import asyncio
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"

# 固定的测试集: 覆盖分数线/院校/专业/就业/政策/选科 6 类真实场景。
# 刻意混合了"时效性强"(分数线)和"时效性弱"(选科)的问题,
# 因为这俩对 provider 的要求完全不同 —— 分数线只有新闻类源能答上。
QUERIES = [
    ("分数线", "广东 2025 高考一本线"),
    ("分数线", "湖北 2025 特殊类型招生控制线"),
    ("分数线", "江苏 2025 本科批 投档线"),
    ("院校", "武汉大学 计算机专业 怎么样"),
    ("院校", "华中科技大学 就业情况"),
    ("院校", "广东省内 双一流 高校 排名"),
    ("专业", "人工智能专业 就业前景"),
    ("专业", "土木工程 是不是天坑专业"),
    ("专业", "临床医学 学制 就业"),
    ("就业", "计算机专业 毕业生 薪资 待遇"),
    ("就业", "考公 和 大厂 offer 怎么选"),
    ("政策", "强基计划 报考条件"),
    ("政策", "新高考 3+1+2 选科要求"),
    ("选科", "物理组 和 历史组 有什么区别"),
    ("选科", "选了物理 能报哪些专业"),
]


def _load_module(name, relpath):
    path = BACKEND / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _install_stubs(provider_delay=0.0, success=()):
    """自检模式: 桩掉 app.* 依赖与 provider, 不碰网络"""
    import types

    app = types.ModuleType("app"); app.__path__ = []
    agent = types.ModuleType("app.agent"); agent.__path__ = []
    core = types.ModuleType("app.core"); core.__path__ = []
    search = types.ModuleType("app.agent.search"); search.__path__ = []

    config = types.ModuleType("app.core.config")
    class _S:
        WEB_SEARCH_ENABLED = True
        TAVILY_API_KEY = "stub"   # 让 tavily 也进候选, 验证 provider 契约
    config.settings = _S()
    core.config = config

    qb = _load_module("_bq", "app/agent/search/query_builder.py")
    uf = types.ModuleType("app.agent.search.url_fetcher")
    async def _fetch(url, max_chars=6000):
        return {"success": True, "url": url, "text": ""}
    uf.fetch_url = _fetch
    search.url_fetcher = uf

    prov = types.ModuleType("app.agent.search.providers")
    prov._self_test_delay = provider_delay
    prov._self_test_success = set(success)
    for name in ("tavily_search", "bing_html_search", "duckduckgo_search",
                 "baidu_search", "wikipedia_search", "arxiv_search"):
        setattr(prov, name, _make_stub_provider(name, provider_delay, set(success)))
    search.providers = prov

    for m, mod in [("app", app), ("app.agent", agent), ("app.core", core),
                   ("app.core.config", config), ("app.agent.search", search),
                   ("app.agent.search.query_builder", qb),
                   ("app.agent.search.url_fetcher", uf),
                   ("app.agent.search.providers", prov)]:
        sys.modules[m] = mod

    ws = _load_module("_bws", "app/agent/search/web_search.py")
    sys.modules["app.agent.search"].web_search = ws
    return ws


def _make_stub_provider(name, delay, success):
    async def _fn(query, max_results=10, time_hint=None):
        if delay:
            await asyncio.sleep(delay)
        if name in success:
            return {"success": True, "provider": name, "query": query,
                    "results": [{"title": f"{name}-{query[:12]}",
                                 "url": f"https://stub.invalid/{name}/{abs(hash(query))%9999}",
                                 "content": "桩内容 " * 30}]}
        return {"success": False, "provider": name, "query": query,
                "results": [], "error": "stub: not configured"}
    _fn.__name__ = name
    return _fn


async def _collect(ws, queries, max_results=5):
    records = []
    for category, q in queries:
        t0 = time.monotonic()
        try:
            res = await ws.web_search(q, max_results=max_results)
            elapsed = round(time.monotonic() - t0, 2)
            records.append({
                "category": category,
                "query": q,
                "success": bool(res.get("success")),
                "n_results": len(res.get("results", [])),
                "elapsed": elapsed,
                "budget_exhausted": res.get("budget_exhausted", False),
                "providers": {p["name"]: {"ok": p["ok"], "count": p["count"],
                                          "elapsed": p.get("elapsed", 0),
                                          "error": p.get("error") or ""}
                              for p in res.get("providers_tried", [])},
            })
        except Exception as e:
            records.append({"category": category, "query": q, "success": False,
                            "n_results": 0, "elapsed": round(time.monotonic() - t0, 2),
                            "error": f"{type(e).__name__}: {e}"})
    return records


def _summarize(records):
    total = len(records)
    ok = sum(1 for r in records if r["success"])
    times = sorted(r["elapsed"] for r in records)

    def pct(p):
        if not times:
            return 0.0
        idx = min(len(times) - 1, int(len(times) * p))
        return times[idx]

    per_provider = {}
    for r in records:
        for pname, pinfo in (r.get("providers") or {}).items():
            slot = per_provider.setdefault(pname, {"ok": 0, "total": 0, "results": 0, "times": []})
            slot["total"] += 1
            if pinfo["ok"]:
                slot["ok"] += 1
            slot["results"] += pinfo["count"]
            slot["times"].append(pinfo["elapsed"])

    for slot in per_provider.values():
        slot["success_rate"] = round(slot["ok"] / slot["total"], 3) if slot["total"] else 0.0
        slot["avg_elapsed"] = round(statistics.mean(slot["times"]), 2) if slot["times"] else 0.0
        slot["avg_results"] = round(slot["results"] / slot["total"], 1) if slot["total"] else 0.0

    return {
        "queries": total,
        "success": ok,
        "success_rate": round(ok / total, 3) if total else 0.0,
        "p50_elapsed": pct(0.5),
        "p95_elapsed": pct(0.95),
        "max_elapsed": max(times) if times else 0.0,
        "budget_exhausted_count": sum(1 for r in records if r.get("budget_exhausted")),
        "per_provider": per_provider,
    }


def _print_table(records, summary):
    print("\n" + "=" * 74)
    print(f"{'类别':<8}{'query':<34}{'OK':<5}{'条数':<6}{'耗时(s)'}")
    print("-" * 74)
    for r in records:
        mark = "✓" if r["success"] else "✗"
        print(f"{r['category']:<8}{r['query'][:32]:<34}{mark:<5}"
              f"{r['n_results']:<6}{r['elapsed']}")
    print("=" * 74)
    print(f"整体成功率 : {summary['success']}/{summary['queries']} "
          f"({summary['success_rate']:.0%})")
    print(f"耗时       : p50={summary['p50_elapsed']}s  p95={summary['p95_elapsed']}s  "
          f"max={summary['max_elapsed']}s")
    if summary["budget_exhausted_count"]:
        print(f"⚠️ 触发时间预算提前收尾: {summary['budget_exhausted_count']} 次")
    print("\n各源表现:")
    print(f"  {'provider':<14}{'成功率':<10}{'均耗时':<9}{'均条数'}")
    for name, s in sorted(summary["per_provider"].items(),
                          key=lambda kv: -kv[1]["success_rate"]):
        print(f"  {name:<14}{s['success_rate']:<10.0%}{s['avg_elapsed']:<9}"
              f"{s['avg_results']}")


def _diff_vs_baseline(new_summary, baseline_path):
    p = Path(baseline_path)
    if not p.exists():
        print(f"\n(无历史基线 {p}, 首次记录)")
        return
    old = json.loads(p.read_text(encoding="utf-8")).get("summary", {})
    print(f"\n与基线 {p.name} 对比:")
    for key, label in (("success_rate", "成功率"), ("p50_elapsed", "p50耗时"),
                       ("p95_elapsed", "p95耗时")):
        if key not in old:
            continue
        delta = new_summary[key] - old[key]
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        # 成功率涨是好事, 耗时涨是坏事
        good = (delta > 0) if key == "success_rate" else (delta < 0)
        mark = "✅" if (delta == 0 or good) else "⚠️"
        print(f"  {mark} {label}: {old[key]} → {new_summary[key]} ({arrow}{abs(delta):.3g})")

    for pname, new in sorted(new_summary["per_provider"].items()):
        o = old.get("per_provider", {}).get(pname)
        if not o:
            continue
        d = new["success_rate"] - o["success_rate"]
        if abs(d) >= 0.2:
            print(f"  {'⚠️' if d < 0 else '✅'} {pname} 成功率 {o['success_rate']:.0%} "
                  f"→ {new['success_rate']:.0%}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true",
                    help="真实发起网络请求(需已装依赖)")
    ap.add_argument("--self-test", action="store_true",
                    help="离线自检: 桩 provider, 不碰网络(默认)")
    ap.add_argument("--save", metavar="PATH", help="把结果存为基线 JSON")
    ap.add_argument("--compare", metavar="PATH", help="与某个基线 JSON 对比")
    args = ap.parse_args()

    if args.run:
        # 真实模式: 需要完整依赖, 走正常 import 链路
        sys.path.insert(0, str(BACKEND))
        from app.agent.search import web_search as ws
        print("真实模式: 会对外部站点发起网络请求…")
    else:
        # 自检模式: 全部桩掉
        ws = _install_stubs(
            provider_delay=0.0,
            success=("bing_html_search", "baidu_search", "tavily_search"),
        )
        print("离线自检模式: provider 为桩, 不发网络请求")

    t0 = time.monotonic()
    records = await _collect(ws, QUERIES)
    summary = _summarize(records)
    _print_table(records, summary)
    print(f"\n总耗时: {round(time.monotonic() - t0, 2)}s")

    if args.save:
        Path(args.save).write_text(
            json.dumps({"summary": summary, "records": records},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"基线已保存: {args.save}")
    if args.compare:
        _diff_vs_baseline(summary, args.compare)
    elif not args.save:
        _diff_vs_baseline(summary, args.save or "search_baseline.json")


if __name__ == "__main__":
    asyncio.run(main())
