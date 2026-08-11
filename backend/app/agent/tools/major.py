"""查专业工具 - analyze_major (v0.9.0 接 db/majors.json + KB)
"""
from typing import Dict

from app.agent.tools._loader import load_db, load_kb


async def analyze_major(major_name: str) -> Dict:
    """深度分析专业 (就业/薪资/张老师点评) — 接 db/majors.json + 03_majors.json"""
    # 1. db 大数据
    db_majors = load_db("majors.json")
    found_db = None
    for m in db_majors:
        if major_name in m.get("name", "") or m.get("name", "") in major_name:
            found_db = m
            break

    # 2. KB (张老师点评)
    kb_majors = load_kb("03_majors.json")
    found_kb = None
    for m in kb_majors:
        if major_name in m.get("name", "") or m.get("name", "") in major_name:
            found_kb = m
            break

    if not found_db and not found_kb:
        return {
            "found": False,
            "message": f"没找到 '{major_name}' 的资料。可以试试：计算机、软件工程、金融、会计、法学、临床医学、电气工程、土木工程等",
        }

    return {
        "found": True,
        "name": (found_db or found_kb).get("name"),
        "category": (found_db or found_kb).get("category") or (found_db or found_kb).get("category_zh"),
        "sub_category": (found_db or found_kb).get("sub_category"),
        "is_hot": (found_db or {}).get("is_hot"),
        "employment_rate": (found_db or {}).get("employment_rate") or (found_kb or {}).get("employment_rate"),
        "median_salary": (found_db or {}).get("median_salary") or (found_kb or {}).get("median_salary"),
        "avg_salary": (found_db or {}).get("avg_salary") or (found_kb or {}).get("avg_salary"),
        "postgraduate_rate": (found_db or {}).get("postgraduate_rate") or (found_kb or {}).get("postgraduate_rate"),
        "overseas_rate": (found_db or {}).get("overseas_rate"),
        "job_directions": (found_db or {}).get("job_directions"),
        "description": (found_db or {}).get("description"),
        "zxf_comment": (found_kb or {}).get("comment"),
        "warning": (found_kb or {}).get("warning"),
        "data_source": "db/majors.json (585个) + KB 03_majors.json (张老师点评)",
    }
