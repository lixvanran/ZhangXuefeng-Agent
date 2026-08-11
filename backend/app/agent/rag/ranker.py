"""相似度排序 - cosine + 关键词打分
"""
import math
from typing import List, Dict, Set


def cosine(a: List[float], b: List[float]) -> float:
    """cosine 相似度"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def keyword_score(query_tokens: Set[str], content: str) -> float:
    """关键词打分 - 长 token 权重更高
    - 4+ 字符 token: 权重 2
    - 2-3 字符 token: 权重 1
    """
    if not query_tokens or not content:
        return 0.0
    content_lower = content.lower()
    score = 0
    for tok in query_tokens:
        if len(tok) > 1 and tok in content_lower:
            count = content_lower.count(tok)
            score += count * (2 if len(tok) >= 4 else 1)
    return score
