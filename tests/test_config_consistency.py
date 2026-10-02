"""配置一致性检查 — 纯标准库 + AST 静态分析, 不需要运行时依赖。

跑法 (在项目根目录):
    python3 tests/test_config_consistency.py
"""
import ast
import os
import re
import unittest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
REPO = os.path.dirname(BACKEND)


def _py_files():
    for dirpath, dirnames, filenames in os.walk(os.path.join(BACKEND, "app")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestNoDeadTierEnvConfig(unittest.TestCase):
    """TIER_MODEL_* / TIER_FALLBACK_* 是死配置 —— 没有任何代码读它们

    历史: README v0.9.2 写"env 仅作兜底", 实际上 v0.9.3 改成读 DB 之后
    env 兜底也没了。这批变量留在 config.py 和两份 .env.example 里,
    会让人以为改 .env 能调档位模型, 实际毫无效果。
    本测试锁住"没人读"这个事实, 并要求 config.py 里有废弃标注。
    """

    DEAD = ("TIER_MODEL_LOW", "TIER_MODEL_MEDIUM", "TIER_MODEL_HIGH",
            "TIER_FALLBACK_LOW", "TIER_FALLBACK_MEDIUM", "TIER_FALLBACK_HIGH")

    def test_nothing_reads_these_settings_attributes(self):
        offenders = []
        for path in _py_files():
            if path.endswith("config.py"):
                continue  # 定义处不算
            src = _read(path)
            for name in self.DEAD:
                # 匹配 settings.NAME / self.NAME / get(..., "NAME")
                for pat in (rf"settings\.{name}\b", rf"self\.{name}\b",
                            rf"getattr\([^)]*[\"']{name}[\"']", rf"[\"']{name}[\"']"):
                    if re.search(pat, src):
                        offenders.append(f"{os.path.relpath(path, REPO)}: {name}")
        self.assertEqual(
            sorted(set(offenders)), [],
            "这些 TIER_* 变量本应是死配置, 却被读取了 —— 如果是新功能请同时更新本测试和文档")

    def test_config_marks_them_deprecated(self):
        src = _read(os.path.join(BACKEND, "app/core/config.py"))
        self.assertIn("已废弃", src, "config.py 里 TIER_MODEL_* 必须标注已废弃, 否则仍会误导用户")

    def test_env_examples_warn(self):
        for p in (".env.example", "backend/.env.example"):
            src = _read(os.path.join(REPO, p))
            self.assertIn("已废弃", src, f"{p} 未标注 TIER_MODEL_* 已废弃")


class TestEnvExampleSync(unittest.TestCase):
    """两份 .env.example 曾经互相冲突, 且没人知道哪份权威"""

    def test_backend_example_is_authoritative_and_says_so(self):
        src = _read(os.path.join(REPO, ".env.example"))
        # config.py 先加载根 .env 再加载 backend/.env 且 override=True
        # → backend/.env 才是最终生效的那份
        self.assertIn("backend/.env", src,
                      "根 .env.example 应说明自己会被 backend/.env 覆盖")

    def test_config_load_order_is_documented(self):
        src = _read(os.path.join(BACKEND, "app/core/config.py"))
        self.assertIn("override=True", src)


class TestProviderContractInRealFiles(unittest.TestCase):
    """所有真实 provider 必须接受 (query, max_results, time_hint)

    web_search 无条件下发 time_hint=, 少一个参数就是 TypeError,
    而它被宽 except 吞成 warning → 该源静默死亡且无人察觉。
    """

    PROVIDERS = ("tavily", "bing", "duckduckgo", "baidu", "wikipedia", "arxiv")

    def test_all_providers_accept_time_hint(self):
        import importlib.util
        bad = []
        for p in self.PROVIDERS:
            path = os.path.join(BACKEND, f"app/agent/search/providers/{p}.py")
            tree = ast.parse(_read(path))
            for node in tree.body:
                if isinstance(node, ast.AsyncFunctionDef) and node.name.endswith("_search"):
                    args = [a.arg for a in node.args.args]
                    if "time_hint" not in args:
                        bad.append(f"{p}.{node.name}{tuple(args)}")
        self.assertEqual(bad, [], f"这些 provider 缺 time_hint 参数, 调用时会 TypeError: {bad}")


class TestNoSilentSwallowOfToolErrors(unittest.TestCase):
    """工具执行层不能裸 await —— 必须有超时上限

    历史上 execute_tool 无任何超时, 一个慢的 search_web 就能把整轮对话挂死,
    这正是 v0.9.7 "错题卡死" 的根因。
    """

    def test_execute_tool_calls_has_timeout(self):
        src = _read(os.path.join(BACKEND, "app/agent/pipeline/llm_runner.py"))
        self.assertIn("asyncio.wait_for", src,
                      "_execute_tool_calls 缺超时上限, 慢工具会挂死整个对话")
        self.assertIn("tool_timeout", src, "超时后应返回结构化降级结果给 LLM")

    def test_timeout_table_exists(self):
        src = _read(os.path.join(BACKEND, "app/agent/pipeline/llm_runner.py"))
        self.assertIn("TOOL_TIMEOUTS", src, "应按工具类型区分超时上限")


class TestSearchHasTimeBudget(unittest.TestCase):
    """搜索必须有全局时间预算, 否则子搜索会叠加成几分钟"""

    def test_budget_constant_and_usage(self):
        src = _read(os.path.join(BACKEND, "app/agent/search/web_search.py"))
        self.assertIn("SEARCH_TIME_BUDGET_SEC", src)
        self.assertIn("deadline", src, "预算必须真正参与调度, 而不只是定义一个常量")

    def test_variants_are_concurrent(self):
        """变体循环必须并发 —— 顺序 for 会让墙钟 = 变体数 × 单次耗时"""
        src = _read(os.path.join(BACKEND, "app/agent/search/web_search.py"))
        tree = ast.parse(src)
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.AsyncFunctionDef)
                   and n.name == "_try_provider_for_all_candidates"), None)
        self.assertIsNotNone(fn)
        has_gather = any(isinstance(n, ast.Await) and isinstance(n.value, ast.Call)
                         and getattr(n.value.func, "attr", "") == "gather"
                         for n in ast.walk(fn))
        self.assertTrue(has_gather, "query 变体必须用 asyncio.gather 并发, 不能顺序 for")


if __name__ == "__main__":
    unittest.main(verbosity=2)
