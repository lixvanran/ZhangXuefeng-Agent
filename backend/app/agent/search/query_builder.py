"""多 query 变体生成 + 时间信号提取
v0.7.9.3 fix: 长 query 在 Bing 经常返回 0/差结果, 用更短的变体 + 官方全称备份
"""
import re
from datetime import datetime
from typing import List, Tuple, Dict


def rewrite_query(query: str, now: datetime = None) -> str:
    """为'最近/最新'类 query 注入当前年月, 让搜索引擎更相关"""
    if now is None:
        now = datetime.now()
    q = query.strip()
    if not q:
        return q
    if not re.search(r'20\d{2}', q):
        current_year = now.year
        current_month = now.month
        if re.search(r'(最近|最新|近期|前天|昨天|今日|今天|最近一周|这周|本周|近日|上个月|上星期|上月|上周)', q):
            q = f"{q} {current_year}年{current_month}月"
    if len(q) > 80:
        q = q[:80]
    return q


def extract_time_hint(query: str, now: datetime = None) -> Dict:
    """提取时间敏感度, 返回 {recency, now_str, year_month}"""
    if now is None:
        now = datetime.now()
    hint = {
        "recency": None,
        "now_str": now.strftime("%Y-%m-%d"),
        "year_month": now.strftime("%Y年%m月"),
    }
    q = query
    if re.search(r'(今天|今日|刚刚|今晚|今早|现在)', q):
        hint["recency"] = "day"
    elif re.search(r'(最近|这周|本周|昨天|前天|近期|近日)', q):
        hint["recency"] = "week"
    elif re.search(r'(最近一个月|这个月|本月|上月|上个月)', q):
        hint["recency"] = "month"
    elif re.search(r'(今年|这一年|本年|2025年|2024年)', q):
        hint["recency"] = "year"
    return hint


PROVINCES = (
    "北京|上海|天津|重庆|河北|山西|内蒙古|辽宁|吉林|黑龙江|江苏|浙江|"
    "安徽|福建|江西|山东|河南|湖北|湖南|广东|广西|海南|四川|贵州|"
    "云南|西藏|陕西|甘肃|青海|宁夏|新疆|香港|澳门|台湾"
)
SCORE_KEYWORDS = r'(分数线|录取线|一本线|本科线|投档线|省控线|批次线|控制线|特控线|特殊类型)'


def make_queries(query: str, max_results: int = 10) -> List[Tuple[str, Dict]]:
    """生成多 query 变体: 原 query + 改写 + 时间限定 + 分数线特化变体
    Returns [(query_str, time_hint), ...]
    """
    now = datetime.now()
    hint = extract_time_hint(query, now)
    candidates = [query]

    # 改写 (加当前年月)
    rw = rewrite_query(query, now)
    if rw != query:
        candidates.append(rw)

    # 时间限定 (有 recency 信号时)
    if hint["recency"] in ("day", "week", "month") and "site:" not in query:
        candidates.append(f"{query} {hint['now_str']}")

    # 分数线类 query 特化 (用更短/更全称变体)
    if re.search(SCORE_KEYWORDS, query):
        year_m = re.search(r'(20\d{2})', query)
        year = year_m.group(1) if year_m else str(now.year)
        prov_match = re.search(PROVINCES, query)
        if prov_match:
            prov = prov_match.group(0)
            candidates.append(f"{year} {prov} 一本线")
            candidates.append(f"{year} {prov} 高考 录取分数线")
            candidates.append(f"{year} {prov} 普通高校招生 录取控制分数线")
        else:
            candidates.append(f"{year} 高考 各省 一本线 录取分数线")

    return [(c, hint) for c in candidates]
