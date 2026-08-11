"""搜索 provider 统一接口
所有 provider 实现 search(query, max_results, time_hint) -> dict

v0.8.0: 新增 wikipedia + arxiv 两个稳定 API 源
- wikipedia: MediaWiki API, 国内外都通, 概念/定义类问题无敌
- arxiv: 学术论文, 国内外都通, 适合科研/专业类问题
"""
from app.agent.search.providers.base import search_result_template
from app.agent.search.providers.tavily import tavily_search
from app.agent.search.providers.bing import bing_html_search
from app.agent.search.providers.duckduckgo import duckduckgo_search
from app.agent.search.providers.baidu import baidu_search
from app.agent.search.providers.wikipedia import wikipedia_search
from app.agent.search.providers.arxiv import arxiv_search

__all__ = [
    "search_result_template",
    "tavily_search", "bing_html_search", "duckduckgo_search", "baidu_search",
    "wikipedia_search", "arxiv_search",
]
