"""搜索调度层回归测试 — 纯标准库, 不需要 fastapi/httpx/bs4 等三方依赖。

用桩模块把 app.* 依赖替换掉, 直接驱动真实的 web_search 代码路径。

跑法 (在项目根目录):
    python3 tests/test_search_scheduling.py
"""
import asyncio
import os
import sys
import time
import types
import unittest

# ===== 桩: 把 app.agent.search.web_search 的外部依赖替换掉 =====

REPO_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")


def _install_stubs():
    """构造最小 app.* 包骨架, 让 web_search 能被 import"""
    if "app" in sys.modules:
        return
    app = types.ModuleType("app"); app.__path__ = []
    agent = types.ModuleType("app.agent"); agent.__path__ = []
    core = types.ModuleType("app.core"); core.__path__ = []
    search = types.ModuleType("app.agent.search"); search.__path__ = []

    # app.core.config
    config = types.ModuleType("app.core.config")
    class _S:
        WEB_SEARCH_ENABLED = True
        TAVILY_API_KEY = ""
    config.settings = _S()
    core.config = config

    # app.agent.search.query_builder — 无三方依赖, 按文件路径直接加载,
    # 绕开 app.agent.search.__init__ (它会 import 真 web_search -> dotenv)
    import importlib.util
    qb_path = os.path.join(REPO_BACKEND, "app/agent/search/query_builder.py")
    spec = importlib.util.spec_from_file_location("_real_query_builder", qb_path)
    qb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qb)
    search.query_builder = qb

    # app.agent.search.url_fetcher — 桩
    uf = types.ModuleType("app.agent.search.url_fetcher")
    async def _fake_fetch(url, max_chars=6000):
        await asyncio.sleep(0.01)
        return {"success": True, "url": url, "text": "x" * 100}
    uf.fetch_url = _fake_fetch
    search.url_fetcher = uf

    # app.agent.search.providers — 桩, 延迟可控
    prov = types.ModuleType("app.agent.search.providers")
    for name in ("tavily_search", "bing_html_search", "duckduckgo_search",
                 "baidu_search", "wikipedia_search", "arxiv_search"):
        setattr(prov, name, _make_stub_provider(name))
    search.providers = prov

    for m, mod in [("app", app), ("app.agent", agent), ("app.core", core),
                   ("app.core.config", config), ("app.agent.search", search),
                   ("app.agent.search.query_builder", qb),
                   ("app.agent.search.url_fetcher", uf),
                   ("app.agent.search.providers", prov)]:
        sys.modules[m] = mod
    sys.modules["app"].core = core
    sys.modules["app.core"].config = config
    sys.modules["app.agent"].search = search
    sys.modules["app.agent.search"].query_builder = qb
    sys.modules["app.agent.search"].url_fetcher = uf
    sys.modules["app.agent.search"].providers = prov

    # 真代码最后加载 —— 此时 app.* 桩已就位, 其内部 import 才解析得到
    import importlib.util
    ws_path = os.path.join(REPO_BACKEND, "app/agent/search/web_search.py")
    spec2 = importlib.util.spec_from_file_location("_real_web_search", ws_path)
    ws_mod = importlib.util.module_from_spec(spec2)
    sys.modules["_real_web_search"] = ws_mod
    spec2.loader.exec_module(ws_mod)
    sys.modules["app.agent.search"].web_search = ws_mod
    sys.modules["app.agent.search"].providers = prov
    sys.modules["app.agent.search"].web_search = ws_mod


# 每个 provider 的行为由这些全局开关控制, 测试里改
PROVIDER_DELAY = 0.5          # 模拟单次网络请求耗时
PROVIDER_RESULTS = {}         # {provider_name: 是否返回结果}
CALL_COUNTS = {}              # {provider_name: 被调用次数}


def _make_stub_provider(name):
    async def _fn(query, max_results=10, time_hint=None):
        CALL_COUNTS[name] = CALL_COUNTS.get(name, 0) + 1
        await asyncio.sleep(PROVIDER_DELAY)
        if PROVIDER_RESULTS.get(name, False):
            return {
                "success": True, "provider": name, "query": query,
                "results": [{"title": f"{name}-{query[:10]}", "url": f"https://x.com/{name}/{query[:5]}", "content": "内容"}],
            }
        return {"success": False, "provider": name, "query": query, "results": [], "error": "no results"}
    _fn.__name__ = name
    return _fn


_install_stubs()

ws = sys.modules["_real_web_search"]  # 被测的真实模块


def _reset(delay=0.5, providers=None):
    global PROVIDER_DELAY, PROVIDER_RESULTS
    PROVIDER_DELAY = delay
    PROVIDER_RESULTS = providers or {}
    CALL_COUNTS.clear()


class TestProviderContract(unittest.TestCase):
    """所有 provider 必须接受 (query, max_results, time_hint) — 否则会被调用方 TypeError 静默吞掉"""

    def test_all_providers_accept_time_hint(self):
        import inspect
        for name in ("tavily_search", "bing_html_search", "duckduckgo_search",
                     "baidu_search", "wikipedia_search", "arxiv_search"):
            sig = inspect.signature(getattr(sys.modules["app.agent.search.providers"], name))
            with self.subTest(provider=name):
                sig.bind("测试query", 8, time_hint={"recency": None})  # 不抛 TypeError 即通过

    def test_real_tavily_signature_fixed(self):
        """回归测试: 真 tavily_search 曾缺 time_hint, 配了 key 也 100% 静默死亡"""
        import ast
        p = os.path.join(REPO_BACKEND, "app/agent/search/providers/tavily.py")
        with open(p, encoding="utf-8") as f:
            src = f.read()
        fn = next(n for n in ast.parse(src).body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "tavily_search")
        self.assertIn("time_hint", [a.arg for a in fn.args.args],
                      "tavily_search 仍然缺 time_hint 参数 — 会导致配了 TAVILY_API_KEY 也调用失败")


class TestVariantParallelization(unittest.TestCase):
    """v0.10.0: query 变体从顺序 for 改为并发 gather"""

    def test_variants_run_concurrently(self):
        _reset(delay=0.3, providers={n: True for n in
                                     ("bing_html_search", "duckduckgo_search", "baidu_search",
                                      "wikipedia_search", "arxiv_search")})
        # 强制多生成几个 query 变体
        query = "武汉 2026 中考 普高线 一本线 分数线"
        candidates = ws.make_queries(query, 16)
        self.assertGreater(len(candidates), 1, "测试前提: 该 query 应产生多个变体")

        t0 = time.monotonic()
        results = asyncio.run(ws._try_provider_for_all_candidates(
            sys.modules["app.agent.search.providers"].bing_html_search, candidates, 8))
        elapsed = time.monotonic() - t0

        n = len(candidates)
        self.assertGreater(len(results), 0)
        # 并发后应接近单次耗时, 而非 n 倍
        self.assertLess(elapsed, PROVIDER_DELAY * n * 0.6,
                        f"变体未并发: {n} 个变体耗时 {elapsed:.2f}s, 单次 {PROVIDER_DELAY}s")


class TestTimeBudget(unittest.TestCase):
    """v0.10.0: 整轮搜索有硬时间预算"""

    def test_budget_is_enforced(self):
        _reset(delay=5.0, providers={})  # 全部源都慢且失败
        original = ws.SEARCH_TIME_BUDGET_SEC
        ws.SEARCH_TIME_BUDGET_SEC = 1.0   # 压到 1s 便于断言
        try:
            t0 = time.monotonic()
            res = asyncio.run(ws.web_search("武汉 2026 中考 分数线", max_results=4))
            elapsed = time.monotonic() - t0
            self.assertFalse(res["success"])
            self.assertIn("providers_tried", res)
            self.assertLess(elapsed, 8.0, f"超出时间预算: 耗时 {elapsed:.2f}s (预算 1s)")
            self.assertIn("elapsed_sec", res)
        finally:
            ws.SEARCH_TIME_BUDGET_SEC = original

    def test_provider_timeout_recorded(self):
        """单个源超时要被记进 providers_tried, 而不是静默消失"""
        _reset(delay=5.0, providers={})
        original_p, original_b = ws.PROVIDER_TIMEOUT_SEC, ws.SEARCH_TIME_BUDGET_SEC
        ws.PROVIDER_TIMEOUT_SEC, ws.SEARCH_TIME_BUDGET_SEC = 0.3, 1.0
        try:
            res = asyncio.run(ws.web_search("测试", max_results=3))
            timed_out = [p for p in res["providers_tried"] if "timeout" in (p.get("error") or "")]
            self.assertGreater(len(timed_out), 0, "超时的 provider 没有被标记")
            for p in res["providers_tried"]:
                self.assertIn("elapsed", p, "providers_tried 缺少耗时字段(可观测性)")
        finally:
            ws.PROVIDER_TIMEOUT_SEC, ws.SEARCH_TIME_BUDGET_SEC = original_p, original_b


class TestSubSearchGating(unittest.TestCase):
    """v0.10.0: 子搜索只在'一个源都没成功'时触发, 不再是'少于 3 条'"""

    def test_sub_search_skipped_when_results_exist(self):
        _reset(delay=0.01, providers={n: True for n in ("bing_html_search",)})
        res = asyncio.run(ws.web_search("北京大学 计算机 分数线", max_results=5))
        self.assertTrue(res["success"])
        self.assertEqual(res["sub_searches"], [],
                         "已有结果时不应再触发子搜索(旧逻辑: <3 条就触发, 白花 1-2 分钟)")

    def test_sub_search_triggers_when_all_fail(self):
        _reset(delay=0.01, providers={})
        res = asyncio.run(ws.web_search("武汉 2026 中考 普高线", max_results=5))
        self.assertFalse(res["success"])


class TestObservability(unittest.TestCase):
    """v0.10.0: 成功路径也要有可观测信息"""

    def test_success_path_exposes_elapsed_and_per_provider(self):
        _reset(delay=0.01, providers={n: True for n in ("bing_html_search", "baidu_search")})
        res = asyncio.run(ws.web_search("清华大学 计算机", max_results=4))
        self.assertTrue(res["success"])
        self.assertIn("elapsed_sec", res)
        self.assertGreater(len(res["providers_tried"]), 0)
        ok = [p for p in res["providers_tried"] if p["ok"]]
        self.assertGreater(len(ok), 0)
        for p in res["providers_tried"]:
            self.assertIn("elapsed", p)
            self.assertIn("ok", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
