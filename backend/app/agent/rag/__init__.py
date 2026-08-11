"""RAG 模块 - 纯 Python 关键词向量检索
模块结构:
- tokenizer.py: 中文分词 + bigram
- indexer.py: 向量化 (TF-IDF 简化版) + 知识库加载
- ranker.py: cosine 相似度排序
- boost.py: 实体 boost（省+年份直接命中）
- engine.py: 入口 ZhangRAG, 对外暴露
"""
from app.agent.rag.engine import ZhangRAG, rag_engine, embedding_service

__all__ = ["ZhangRAG", "rag_engine", "embedding_service"]
