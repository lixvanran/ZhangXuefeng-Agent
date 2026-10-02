"""测试用的 web_search 桩环境 — 被多个测试文件共享

## 为什么需要共享

`web_search.py` 在 import 时就把 provider 函数**绑定了**:
```python
from app.agent.search.providers import bing_html_search, ...
```
所以单纯换掉 `sys.modules` 里的 provider 并不会改变已导入模块的行为 ——
这正是两个测试文件各自装桩后互相打架的原因(谁先加载谁赢, 后加载的
拿不到自己期望的 provider 行为)。

解法: provider 做成**可变分发器** —— 只有一个函数对象, 行为由
`set_behavior()` 在运行时切换。桩只装一次, 各测试文件按需改行为。

跑法: 由各测试文件 import, 不单独执行。
"""
import asyncio
import importlib.util
import os
import sys
import types

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")

# 当前 provider 行为(由 set_behavior 改写)
_state = {
    "delay": 0.0,
    "success": frozenset(),
    "counter": 0,
}

PROVIDER_NAMES = ("tavily_search", "bing_html_search", "duckduckgo_search",
                  "baidu_search", "wikipedia_search", "arxiv_search")


def set_behavior(delay=0.0, success=()):
    """设置 provider 桩的行为

    delay   : 每个 provider 模拟的网络耗时(秒)
    success : 返回结果的 provider 名集合
    """
    _state["delay"] = delay
    _state["success"] = frozenset(success)
    _state["counter"] = 0


def call_counts():
    return dict(_state.get("counts", {}))


def _dispatcher(name):
    async def _fn(query, max_results=10, time_hint=None):
        counts = _state.setdefault("counts", {})
        counts[name] = counts.get(name, 0) + 1
        if _state["delay"]:
            await asyncio.sleep(_state["delay"])
        if name in _state["success"]:
            return {
                "success": True, "provider": name, "query": query,
                "results": [{
                    "title": f"{name}-{query[:12]}",
                    "url": f"https://stub.invalid/{name}/{abs(hash(query)) % 9999}",
                    "content": "桩内容 " * 30,
                }],
            }
        return {"success": False, "provider": name, "query": query,
                "results": [], "error": "stub: not configured"}
    _fn.__name__ = name
    return _fn


def _load(name, rel):
    path = os.path.join(BACKEND, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _install():
    app = types.ModuleType("app"); app.__path__ = []
    agent = types.ModuleType("app.agent"); agent.__path__ = []
    core = types.ModuleType("app.core"); core.__path__ = []
    search = types.ModuleType("app.agent.search"); search.__path__ = []

    config = types.ModuleType("app.core.config")

    class _Settings:
        WEB_SEARCH_ENABLED = True
        TAVILY_API_KEY = ""      # 默认不带 key, tavily 不进候选
    config.settings = _Settings()
    core.config = config

    qb = _load("_stub_qb", "app/agent/search/query_builder.py")
    search.query_builder = qb

    uf = types.ModuleType("app.agent.search.url_fetcher")

    async def _fetch(url, max_chars=6000):
        await asyncio.sleep(0.01)
        return {"success": True, "url": url, "text": "x" * 100}
    uf.fetch_url = _fetch
    search.url_fetcher = uf

    prov = types.ModuleType("app.agent.search.providers")
    for n in PROVIDER_NAMES:
        setattr(prov, n, _dispatcher(n))
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

    ws = _load("_real_web_search", "app/agent/search/web_search.py")
    sys.modules["app.agent.search"].web_search = ws
    return ws


ws = _install()   # 模块级只装一次
