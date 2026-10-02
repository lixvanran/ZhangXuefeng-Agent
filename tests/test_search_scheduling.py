"""搜索调度层回归测试 — 纯标准库, 不需要 fastapi/httpx/bs4 等三方依赖。

桩环境见 tests/_search_stubs.py(与 test_search_relevance.py 共享)。
provider 是可变分发器, 由 set_behavior() 在运行时切换行为。

跑法 (在项目根目录):
    python3 tests/test_search_scheduling.py
"""
import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _search_stubs import ws, set_behavior  # noqa: E402  共享桩环境

REPO_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")

ALL = ("tavily_search", "bing_html_search", "duckduckgo_search",
       "baidu_search", "wikipedia_search", "arxiv_search")


def _reset(delay=0.5, providers=()):
    set_behavior(delay=delay, success=providers)


class TestProviderContract(unittest.TestCase):
    """所有 provider 必须接受 (query, max_results, time_hint) — 否则会被调用方 TypeError 静默吞掉"""

    def test_all_providers_accept_time_hint(self):
        import inspect
        from _search_stubs import PROVIDER_NAMES
        for name in PROVIDER_NAMES:
            sig = inspect.signature(getattr(sys.modules["app.agent.search.providers"], name))
            with self.subTest(provider=name):
                sig.bind("测试query", 8, time_hint={"recency": None})

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

    def setUp(self):
        _reset(delay=0.3, providers=("bing_html_search",))

    def test_variants_run_concurrently(self):
        query = "武汉 2026 中考 普高线 一本线 分数线"
        candidates = ws.make_queries(query, 16)
        self.assertGreater(len(candidates), 1, "测试前提: 该 query 应产生多个变体")

        t0 = time.monotonic()
        results = asyncio.run(ws._try_provider_for_all_candidates(
            sys.modules["app.agent.search.providers"].bing_html_search,
            candidates, 8))
        elapsed = time.monotonic() - t0

        n = len(candidates)
        self.assertGreater(len(results), 0)
        # 并发后应接近单次耗时, 而非 n 倍
        self.assertLess(elapsed, 0.3 * n * 0.6,
                        f"变体未并发: {n} 个变体耗时 {elapsed:.2f}s, 单次 0.3s")


class TestTimeBudget(unittest.TestCase):
    """v0.10.0: 整轮搜索有硬时间预算"""

    def test_budget_is_enforced(self):
        _reset(delay=5.0)          # 全部源都慢且失败
        original = ws.SEARCH_TIME_BUDGET_SEC
        ws.SEARCH_TIME_BUDGET_SEC = 1.0
        try:
            t0 = time.monotonic()
            res = asyncio.run(ws.web_search("武汉 2026 中考 分数线", max_results=4))
            elapsed = time.monotonic() - t0
            self.assertFalse(res["success"])
            self.assertLess(elapsed, 8.0, f"超出时间预算: 耗时 {elapsed:.2f}s (预算 1s)")
            self.assertIn("elapsed_sec", res)
        finally:
            ws.SEARCH_TIME_BUDGET_SEC = original

    def test_provider_timeout_recorded(self):
        _reset(delay=5.0)
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
        _reset(delay=0.01, providers=("bing_html_search",))
        res = asyncio.run(ws.web_search("北京大学 计算机 分数线", max_results=5))
        self.assertTrue(res["success"], res.get("error"))
        self.assertEqual(res["sub_searches"], [],
                         "已有结果时不应再触发子搜索(旧逻辑: <3 条就触发, 白花 1-2 分钟)")

    def test_sub_search_triggers_when_all_fail(self):
        _reset(delay=0.01)
        res = asyncio.run(ws.web_search("武汉 2026 中考 普高线", max_results=5))
        self.assertFalse(res["success"])


class TestObservability(unittest.TestCase):
    """v0.10.0: 成功路径也要有可观测信息"""

    def setUp(self):
        _reset(delay=0.01, providers=("bing_html_search", "baidu_search"))

    def test_success_path_exposes_elapsed_and_per_provider(self):
        res = asyncio.run(ws.web_search("清华大学 计算机", max_results=4))
        self.assertTrue(res["success"], res.get("error"))
        self.assertIn("elapsed_sec", res)
        self.assertIn("relevance", res)
        self.assertIn("low_relevance", res)
        ok = [p for p in res["providers_tried"] if p["ok"]]
        self.assertGreater(len(ok), 0)
        for p in res["providers_tried"]:
            self.assertIn("elapsed", p)
            self.assertIn("ok", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
