"""联网搜索模块
- query_builder.py: 多 query 变体生成
- url_fetcher.py: 抓全文
- providers/: 各搜索源 (tavily, bing, duckduckgo, baidu)
- web_search.py: 入口, 统一调度各 provider
"""
from app.agent.search.web_search import web_search, fetch_url
from app.agent.search.query_builder import make_queries, rewrite_query, extract_time_hint

__all__ = ["web_search", "fetch_url", "make_queries", "rewrite_query", "extract_time_hint"]
