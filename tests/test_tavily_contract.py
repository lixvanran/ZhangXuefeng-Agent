"""Tavily API 契约锁定 — 纯 AST/静态检查, 不需要依赖或网络。

## 为什么需要

Tavily 这个源修好签名、真正能跑之后, 才暴露出第二个更隐蔽的问题:
**参数名写错了也不会报错**。Tavily 对未知字段静默忽略, 于是功能"看起来在工作",
实际永远拿不到时效性过滤。

本轮实测教训: 第一版修复把 recency 映射到 `days`, 但 Tavily 官方 API
**根本没有 `days` 这个参数**, 只有 `time_range`(枚举 day/week/month/year)。
依据: https://docs.tavily.com/documentation/api-reference/endpoint/search

## 附带锁定

`TAVILY_API_KEY` 的设置方式也被锁定 —— 官方文档要求 `Authorization: Bearer <key>`。
原来只在 body 里放 `api_key`, 属于旧版用法, 现同时带 Bearer 头与 body 字段。

跑法 (在项目根目录):
    python3 tests/test_tavily_contract.py
"""
import ast
import os
import unittest

TAVILY_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "backend", "app", "agent", "search", "providers", "tavily.py",
)

# Tavily 官方 POST /search 的时间过滤参数
VALID_TIME_RANGES = {"day", "week", "month", "year"}


def _source():
    with open(TAVILY_PY, encoding="utf-8") as f:
        return f.read()


def _payload_keys():
    """抽出构造 payload 时写入的所有 key"""
    tree = ast.parse(_source())
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


class TestTavilyParameterContract(unittest.TestCase):
    def test_uses_time_range_not_days(self):
        """`days` 不是 Tavily 的参数, 写了会被静默忽略"""
        src = _source()
        self.assertNotIn('"days"', src,
                         "tavily 仍在用 `days` —— 该参数不存在于 Tavily API, "
                         "应使用 `time_range`(day/week/month/year)")
        self.assertNotIn("payload[\"days\"]", src)

    def test_time_range_is_set_from_recency(self):
        src = _source()
        self.assertIn("time_range", src, "recency 提示没有映射到 time_range")

    def test_time_range_values_are_valid_enum(self):
        """映射表的值必须落在 Tavify 允许的枚举内"""
        tree = ast.parse(_source())
        maps = []
        for node in ast.walk(tree):
            # 找形如 {"day": "day", "week": "week", ...} 的字面量 dict
            if isinstance(node, ast.Dict) and node.keys:
                pairs = {}
                for k, v in zip(node.keys, node.values):
                    if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                            and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                        pairs[k.value] = v.value
                if pairs and any(v in VALID_TIME_RANGES for v in pairs.values()):
                    maps.append(pairs)
        self.assertTrue(maps, "没找到 recency → time_range 的映射表")
        for m in maps:
            for target in m.values():
                self.assertIn(target, VALID_TIME_RANGES,
                              f"映射到非法值 {target!r}, Tavily 只接受 {VALID_TIME_RANGES}")

    def test_topic_only_uses_allowed_values(self):
        """topic 只允许 general / news / finance"""
        import re
        src = _source()
        for val in re.findall(r'topic"?\]?\s*[:=]\s*"([a-z]+)"', src):
            self.assertIn(val, {"general", "news", "finance"},
                          f'topic 取值 {val!r} 不合法')


class TestTavilyAuthContract(unittest.TestCase):
    def test_uses_bearer_authorization_header(self):
        """官方文档要求 Authorization: Bearer <key>"""
        src = _source()
        self.assertIn("Authorization", src,
                      "缺少 Authorization 头 —— Tavily 官方要求 Bearer 鉴权")
        self.assertIn("Bearer", src, "Authorization 头应为 Bearer 形式")

    def test_keeps_body_api_key_for_backcompat(self):
        """同时保留 body 里的 api_key, 兼容仍接受该字段的部署"""
        src = _source()
        self.assertIn("api_key", src, "body 里的 api_key 字段被移除了, 会破坏对旧部署的兼容")


class TestTavilySignatureStillFixed(unittest.TestCase):
    """守住 v0.10.0 的第一个修复: 签名缺 time_hint 会让该源 100% 静默死亡"""

    def test_accepts_time_hint(self):
        tree = ast.parse(_source())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "tavily_search")
        self.assertIn("time_hint", [a.arg for a in fn.args.args],
                      "tavily_search 缺 time_hint —— 调用方无条件下发该关键字, "
                      "会 TypeError 并被宽 except 吞掉")


if __name__ == "__main__":
    unittest.main(verbosity=2)
