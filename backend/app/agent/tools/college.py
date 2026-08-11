"""查大学工具 - query_college (v0.9.0 接 db/schools.json)
"""
from typing import Dict

from app.agent.tools._loader import load_db


async def query_college(
    score: int = 0,
    rank: int = 0,
    province: str = "",
    category: str = "理科",
    strategy: str = "稳",
    limit: int = 10,
) -> Dict:
    """按分数+位次+省+科类 推院校 (兼容旧接口, 实际逻辑走 calculate_match)
    - 重定向到 admission.calculate_match 走 db/scores.json
    """
    from app.agent.tools.admission import calculate_match
    if not score:
        return {"found": False, "message": "需要 score 参数"}
    return await calculate_match(
        score=score,
        province=province or "全国",
        subject_type=category,
        strategy=strategy,
        limit=limit,
    )
