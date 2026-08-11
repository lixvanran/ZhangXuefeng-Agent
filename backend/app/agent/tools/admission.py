"""录取相关工具 (v0.9.0 升级 - 接 db/ 大数据)
- calculate_admission_probability: 估算单个院校录取概率
- calculate_match: 按分数+省份+科类 推荐院校 (冲/稳/保) — 接 db/scores.json 8.5万条
- search_policy: 查高考政策 (web + 本地政策库)
- compare_schools: 多院校对比 — 接 db/schools.json
- search_school: 单校查 (按名字)
- search_major: 查专业 — 接 db/majors.json
- query_college: 按分数/位次/省推院校 (旧接口兼容)
- analyze_major: 专业深度分析
"""
from typing import Dict, List, Optional
import logging

from app.agent.tools._loader import load_kb, load_db
from app.agent.search import web_search

logger = logging.getLogger(__name__)


# =================================================================
# v0.9.0 核心: calculate_match 走 db/scores.json 8.5万条
# =================================================================

# 科类归一化: 物理类/历史类(新高考) ↔ 理科/文科(老高考)
_SUBJECT_ALIASES = {
    "物理类": ["物理类", "理科", "理工", "综合"],
    "历史类": ["历史类", "文科", "文史", "综合"],
    "理科": ["理科", "物理类", "理工", "综合"],
    "文科": ["文科", "历史类", "文史", "综合"],
    "综合": ["综合"],
    "理工": ["理工", "理科", "物理类", "综合"],
    "文史": ["文史", "文科", "历史类", "综合"],
}


def _strategy_score_range(strategy: str, score: int) -> tuple:
    """冲/稳/保 → 分数区间"""
    if strategy == "冲":
        return score, score + 30
    if strategy == "保":
        return max(score - 50, 0), score
    # 稳 (default)
    return max(score - 20, 0), score + 10


def _normalize_subject(subject_type: str) -> List[str]:
    return _SUBJECT_ALIASES.get(subject_type, [subject_type])


async def calculate_match(
    score: int,
    province: str,
    subject_type: str = "物理类",
    strategy: str = "稳",
    limit: int = 15,
) -> Dict:
    """按分数+省份+科类 推荐院校 (v0.9.0 走 db/scores.json 8.5万条)

    Args:
        score: 考生分数 (0-750)
        province: 省份, "山东" / "河南" / "江苏"
        subject_type: 科类, 物理类/历史类/理科/文科/综合
        strategy: 冲/稳/保 (默认稳)
        limit: 返回数量 (默认 15)

    Returns:
        {
            "query": {...},
            "matches": [{school, year, min_score, min_rank, probability, level, source}, ...]
        }
    """
    min_s, max_s = _strategy_score_range(strategy, score)
    aliases = _normalize_subject(subject_type)

    # v0.9.0: 走 db/scores.json 8.5万条 (2023-2025 三年真实数据)
    scores = load_db("scores.json")
    school_map: Dict[str, Dict] = {}  # school_name → 最高匹配分的数据

    for s in scores:
        if s.get("province") != province:
            continue
        if s.get("subject_type") not in aliases:
            continue
        m = s.get("min_score")
        if not m:
            continue
        # 落在 ±20 分区间内
        if not (min_s - 20 <= m <= max_s + 20):
            continue
        # 每个学校保留最新一年+最低分
        key = s["school_name"]
        if key not in school_map or s["year"] > school_map[key]["year"]:
            school_map[key] = s

    matches = []
    for sch, s in school_map.items():
        m = s["min_score"]
        if m <= min_s:
            prob, level = 0.85, "稳"
        elif m <= score:
            prob, level = 0.70, "较稳"
        elif m <= max_s:
            prob, level = 0.50, "冲一冲"
        else:
            prob, level = 0.20, "保底可考虑"
        matches.append({
            "school_name": sch,
            "min_score": m,
            "avg_score": s.get("avg_score"),
            "max_score": s.get("max_score"),
            "min_rank": s.get("min_rank"),
            "year": s.get("year"),
            "subject_type": s.get("subject_type"),
            "batch": s.get("batch"),
            "province": s.get("province"),
            "probability": prob,
            "level": level,
        })

    matches.sort(key=lambda x: -x["probability"])
    matches = matches[:limit]

    return {
        "query": {
            "score": score,
            "province": province,
            "subject_type": subject_type,
            "strategy": strategy,
            "score_range": [min_s, max_s],
        },
        "total": len(matches),
        "matches": matches,
        "data_source": "db/scores.json (2023-2025 真实录取数据, 8.5万条)",
        "hint": "基于真实录取数据. 实际请以本省教育考试院最新发布的'一分一段表'为准. 4.0 上岸 ↗",  # 张雪峰经典
    }


# =================================================================
# 兼容旧工具
# =================================================================

async def calculate_admission_probability(
    user_rank: int, college_name: str, major_name: str = "", year: int = 2024
) -> Dict:
    """估算录取概率 (单院校, 用位次比较) — v0.9.0 改走 db/schools.json + db/scores.json"""
    schools = load_db("schools.json")
    scores = load_db("scores.json")

    # 1) 找学校
    school = None
    for s in schools:
        if college_name in s.get("name", ""):
            school = s
            break
    if not school:
        return {"found": False, "message": f"没找到: {college_name}"}

    # 2) 找该校在 2024+ 的 min_rank
    school_scores = [s for s in scores if s.get("school_name") == school["name"] and s.get("year", 0) >= 2024]
    if not school_scores:
        return {
            "found": True,
            "college": school["name"],
            "user_rank": user_rank,
            "probability": 0.5,
            "level": "无数据, 估中等",
            "note": f"该校在 db/scores.json 中暂无 2024+ 录取数据",
        }

    # 取最近年份的 min_rank (理科)
    school_scores.sort(key=lambda x: -x.get("year", 0))
    min_rank = school_scores[0].get("min_rank", 0) or 0
    avg_rank_estimate = min_rank * 1.1 if min_rank else 0

    if user_rank <= min_rank:
        probability, level = 0.95, "稳"
    elif user_rank <= avg_rank_estimate:
        probability, level = 0.70, "较稳"
    elif user_rank <= avg_rank_estimate * 1.1:
        probability, level = 0.40, "冲"
    else:
        probability, level = 0.10, "难"

    return {
        "found": True,
        "college": school["name"],
        "user_rank": user_rank,
        "min_rank_2024": min_rank,
        "probability": probability,
        "level": level,
        "data_source": "db/scores.json",
    }


async def search_policy(province: str = "全国", year: int = 2025, keyword: str = "") -> Dict:
    """查高考政策 (本地 09_policies.json + web 兜底)"""
    policies = load_kb("09_policies.json")
    matched = []
    if keyword:
        for p in policies:
            if keyword in p.get("name", "") or keyword in p.get("summary", ""):
                matched.append(p)
            else:
                for ch in keyword:
                    if ch in p.get("name", ""):
                        matched.append(p)
                        break
    else:
        matched = policies[:5]

    result = {
        "province": province,
        "year": year,
        "keyword": keyword,
        "local_policies": [{
            "id": p.get("id"),
            "name": p.get("name"),
            "type": p.get("type"),
            "summary": p.get("summary"),
            "key_points": p.get("key_points", []),
            "scope": p.get("scope"),
            "zxf_comment": p.get("zxf_comment"),
        } for p in matched[:10]],
    }
    if keyword:
        try:
            web_result = await web_search(f"{year} {province} 高考 {keyword} 政策", max_results=3)
            result["web_results"] = web_result.get("results", [])
            result["web_provider"] = web_result.get("provider", "none")
        except Exception as e:
            logger.warning(f"web search failed: {e}")
    return result


async def compare_schools(school_names: List[str], dimensions: Optional[List[str]] = None) -> Dict:
    """多院校对比 (v0.9.0 走 db/schools.json 3765所)"""
    schools = load_db("schools.json")
    rankings = load_db("subject_rankings.json")
    out = []
    not_found = []
    for name in school_names:
        matched = None
        for s in schools:
            if name in s.get("name", ""):
                matched = s
                break
        if matched:
            # 找该校的王炸学科
            sch_rankings = [r for r in rankings if r.get("school_name") == matched["name"]]
            top_grades = [r for r in sch_rankings if r.get("grade") in ["A+", "A"]]
            top_grades.sort(key=lambda x: 0 if x.get("grade") == "A+" else 1)
            out.append({
                "name": matched["name"],
                "tier": matched.get("level", ""),
                "is_985": matched.get("is_985"),
                "is_211": matched.get("is_211"),
                "is_double_first_class": matched.get("is_double_first_class"),
                "city": matched.get("city"),
                "province": matched.get("province"),
                "school_type": matched.get("school_type", ""),
                "ranking": matched.get("ranking", ""),
                "top_subjects": [{"subject": r.get("major_category"), "grade": r.get("grade")} for r in top_grades[:5]],
                "description": matched.get("description", ""),
            })
        else:
            not_found.append(name)
    if not out:
        return {"found": False, "message": f"没找到任何学校: {school_names}"}
    return {"found": True, "count": len(out), "schools": out, "not_found": not_found}


# =================================================================
# v0.9.0 新增: search_school / search_major
# =================================================================

async def search_school(
    name: str = "",
    province: str = "",
    is_985: bool = False,
    is_211: bool = False,
    school_type: str = "",
    limit: int = 10,
) -> Dict:
    """查院校 (按名字/省/层次) — 接 db/schools.json"""
    schools = load_db("schools.json")
    results = []
    for s in schools:
        if name and name not in s.get("name", ""):
            continue
        if province and s.get("province") != province:
            continue
        if is_985 and not s.get("is_985"):
            continue
        if is_211 and not s.get("is_211"):
            continue
        if school_type and s.get("school_type") != school_type:
            continue
        results.append({
            "name": s["name"],
            "tier": s.get("level", ""),
            "city": s.get("city"),
            "province": s.get("province"),
            "school_type": s.get("school_type"),
            "ranking": s.get("ranking"),
            "is_985": s.get("is_985"),
            "is_211": s.get("is_211"),
            "is_double_first_class": s.get("is_double_first_class"),
        })
    # 排序: 985 > 211 > 双一流 > 普通
    def sort_key(s):
        return (
            0 if s["is_985"] else (1 if s["is_211"] else (2 if s["is_double_first_class"] else 3)),
            s.get("ranking") or 9999,
        )
    results.sort(key=sort_key)
    return {"total": len(results), "results": results[:limit]}


async def search_major(
    name: str = "",
    category: str = "",
    sub_category: str = "",
    is_hot: bool = False,
    limit: int = 10,
) -> Dict:
    """查专业 (按名字/学科门类) — 接 db/majors.json"""
    majors = load_db("majors.json")
    results = []
    for m in majors:
        if name and name not in m.get("name", ""):
            continue
        if category and m.get("category") != category:
            continue
        if sub_category and m.get("sub_category") != sub_category:
            continue
        if is_hot and not m.get("is_hot"):
            continue
        results.append({
            "name": m["name"],
            "category": m.get("category"),
            "sub_category": m.get("sub_category"),
            "is_hot": m.get("is_hot"),
            "employment_rate": m.get("employment_rate"),
            "median_salary": m.get("median_salary"),
            "avg_salary": m.get("avg_salary"),
            "postgraduate_rate": m.get("postgraduate_rate"),
            "description": m.get("description"),
        })
    if is_hot:
        results.sort(key=lambda x: -(x.get("median_salary") or 0))
    return {"total": len(results), "results": results[:limit]}


# =================================================================
# 旧接口兼容
# =================================================================

async def query_college(
    score: int = 0,
    rank: int = 0,
    province: str = "",
    category: str = "物理类",
    strategy: str = "稳",
    limit: int = 10,
) -> Dict:
    """按分数+位次+省+科类 推院校 (兼容旧 call site)"""
    return await calculate_match(score=score, province=province, subject_type=category, strategy=strategy, limit=limit)


async def analyze_major(major_name: str) -> Dict:
    """深度分析一个专业 — 接 db/majors.json + KB 03_majors.json"""
    # 1. 查 db
    db_majors = load_db("majors.json")
    found_db = None
    for m in db_majors:
        if major_name in m.get("name", ""):
            found_db = m
            break

    # 2. 查 KB (张老师点评)
    kb_majors = load_kb("03_majors.json")
    found_kb = None
    for m in kb_majors:
        if major_name in m.get("name", ""):
            found_kb = m
            break

    if not found_db and not found_kb:
        return {"found": False, "message": f"没找到专业: {major_name}"}

    return {
        "found": True,
        "major_name": (found_db or found_kb).get("name"),
        "category": (found_db or found_kb).get("category") or (found_db or found_kb).get("category_zh"),
        "sub_category": (found_db or found_kb).get("sub_category"),
        "employment_rate": (found_db or {}).get("employment_rate") or (found_kb or {}).get("employment_rate"),
        "median_salary": (found_db or {}).get("median_salary") or (found_kb or {}).get("median_salary"),
        "avg_salary": (found_db or {}).get("avg_salary"),
        "postgraduate_rate": (found_db or {}).get("postgraduate_rate") or (found_kb or {}).get("postgraduate_rate"),
        "is_hot": (found_db or {}).get("is_hot"),
        "job_directions": (found_db or {}).get("job_directions"),
        "description": (found_db or {}).get("description"),
        "zxf_comment": (found_kb or {}).get("comment"),
        "warning": (found_kb or {}).get("warning"),
        "data_source": "db/majors.json (8.5万条) + KB 03_majors.json (张老师点评)",
    }
