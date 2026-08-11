"""搜索 provider 通用工具 - 中文过滤 / 垃圾结果过滤 / 模板"""
import re
from typing import Dict, Any


def has_chinese(text: str) -> bool:
    """字符串是否含中文字符"""
    if not text:
        return False
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


JUNK_DOMAINS = [
    "google.com/search", "google.co/search",
    "bing.com/search", "baidu.com/s",
    "duckduckgo.com", "yahoo.com/search",
]
# v0.8.0: 移除 wikipedia.org/wiki/ — 现在我们用 Wikipedia API, 文章页是有效结果
#   之前这个规则是因为没用 Wiki API, wiki 链接是搜索页, 没用
#   现在 wiki API 直接返回文章 URL, 反而是高质量结果
JUNK_TITLES = ("google", "bing", "百度一下", "百度首页", "必应")
JUNK_CONTENT_SNIPPETS = (
    "we would like to show you a description",
    "the site won’t allow us",
    "the site won't allow us",
)


def is_junk_result(r: dict) -> bool:
    """搜索结果是否垃圾/占位"""
    title = (r.get("title") or "").lower()
    url = (r.get("url") or "").lower()
    content = (r.get("content") or "").lower()
    for d in JUNK_DOMAINS:
        if d in url and "search" in url:
            return True
    if title in JUNK_TITLES:
        return True
    for s in JUNK_CONTENT_SNIPPETS:
        if s in content:
            return True
    return False


def filter_chinese_results(results: list) -> list:
    """只保留含中文 + 非垃圾的结果 (中文 query 必备)"""
    out = []
    for r in results:
        if is_junk_result(r):
            continue
        if has_chinese(r.get("title", "")) or has_chinese(r.get("content", "")):
            out.append(r)
    return out


def search_result_template(provider: str, query: str) -> Dict[str, Any]:
    """统一返回结构"""
    return {
        "success": False,
        "provider": provider,
        "query": query,
        "results": [],
        "error": None,
    }
