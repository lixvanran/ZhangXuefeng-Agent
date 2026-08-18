"""gaokao_client.py — 掌上高考 API 客户端 (v0.9.8 新增)
参考: https://github.com/aster2024/zhangxuefeng_agent (核心数据源)

API 文档 (逆向自 gaokao.cn 前端 JS):
- Base URL: https://api.zjzw.cn/web/api/
- 公共 API, 免 key, 合理使用 (有 SQLite 缓存)
- 关键接口:
  - apidata/api/gkv3/school/lists        → 院校搜索 (keyword 参数)
  - apidata/api/gk/score/province        → 分省录取分数线 (min_section = 位次)
  - apidata/api/gkv3/score/province/rank → 一分一段位次表
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 省份名 → province_id 映射 (国家行政区划代码前两位)
# ---------------------------------------------------------------------------
PROVINCE_ID_MAP = {
    "北京": 11, "天津": 12, "河北": 13, "山西": 14, "内蒙古": 15,
    "辽宁": 21, "吉林": 22, "黑龙江": 23,
    "上海": 31, "江苏": 32, "浙江": 33, "安徽": 34, "福建": 35,
    "江西": 36, "山东": 37,
    "河南": 41, "湖北": 42, "湖南": 43, "广东": 44, "广西": 45, "海南": 46,
    "重庆": 50, "四川": 51, "贵州": 52, "云南": 53, "西藏": 54,
    "陕西": 61, "甘肃": 62, "青海": 63, "宁夏": 64, "新疆": 65,
}

_BASE = "https://api.zjzw.cn/web/api/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.gaokao.cn/",
}
_TIMEOUT = 15
_CACHE_TTL = 7 * 24 * 3600  # 7 天

# ---------------------------------------------------------------------------
# SQLite 缓存 — 避免重复请求, 保护公共 API
# ---------------------------------------------------------------------------
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "gaokao_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_DB = _CACHE_DIR / "cache.db"


def _init_cache():
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expire_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_cache()


def _cache_get(key: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(str(_CACHE_DB))
        row = conn.execute(
            "SELECT value, expire_at FROM cache WHERE key=?", (key,)
        ).fetchone()
        conn.close()
        if row and row[1] > time.time():
            return json.loads(row[0])
    except Exception as e:
        logger.warning(f"cache_get failed: {e}")
    return None


def _cache_set(key: str, value: dict, ttl: int = _CACHE_TTL):
    try:
        conn = sqlite3.connect(str(_CACHE_DB))
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expire_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), int(time.time()) + ttl),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"cache_set failed: {e}")


# ---------------------------------------------------------------------------
# HTTP 请求
# ---------------------------------------------------------------------------
async def _get(params: dict, use_cache: bool = True) -> dict:
    """发一次 GET 请求, 返回解析后的 JSON。失败返回 {}. 默认走缓存"""
    cache_key = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    qs = urllib.parse.urlencode(params)
    url = f"{_BASE}?{qs}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == "0000":
                _cache_set(cache_key, data)
                return data
    except Exception as e:
        logger.warning(f"gaokao_api get failed: url={url[:120]}, err={e}")
    return {}


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------
async def lookup_school_id(name: str) -> Optional[dict]:
    """根据院校名称查找学校信息
    Returns: {"school_id": 118, "name": "苏州大学", "province": "江苏", "city": "苏州市", "f985": 2, "f211": 1, ...}
    """
    if not name:
        return None
    data = await _get({
        "uri": "apidata/api/gkv3/school/lists",
        "keyword": name,
        "page": 1,
        "size": 5,
    })
    items = data.get("data", {}).get("item", [])
    # 优先精确匹配
    for item in items:
        if item.get("name") == name:
            return _format_school(item)
    # 退而求其次: 第一个结果
    if items:
        return _format_school(items[0])
    return None


def _format_school(item: dict) -> dict:
    """格式化院校信息"""
    return {
        "school_id": int(item.get("school_id", 0)),
        "name": item.get("name", ""),
        "province": item.get("province_name", ""),
        "city": item.get("city_name", ""),
        "nature": item.get("nature_name", ""),  # 公办/民办
        "level": item.get("level_name", ""),  # 本科/专科
        "type": item.get("type_name", ""),  # 综合/理工/师范
        "f985": item.get("f985", 0),  # 0/1/2
        "f211": item.get("f211", 0),
        "doublehigh": item.get("doublehigh", "0"),
        "dual_class_name": item.get("dual_class_name", ""),
        "rank": item.get("rank", ""),  # 院校排名
        "school_code": item.get("code_enroll", ""),
    }


async def get_admission_ranks(
    school_id: int,
    province_id: int,
    years: Optional[list] = None,
) -> dict:
    """并发获取指定院校在指定生源省份的历年最低录取位次

    Returns: {2024: {"min_score": 594, "min_rank": 26574, "batch": "普通类一段", "type": "综合"}, 2023: {...}, ...}
    """
    if years is None:
        years = [2024, 2023, 2022]
    async def _fetch_year(year: int) -> tuple:
        data = await _get({
            "uri": "apidata/api/gk/score/province",
            "school_id": school_id,
            "local_province_id": province_id,
            "year": year,
            "page": 1,
            "size": 20,
        })
        items = data.get("data", {}).get("item", [])
        if not items:
            return year, None
        # 多条记录取最低位次
        ranks = []
        for it in items:
            try:
                ms = it.get("min_section")
                if ms and str(ms).lstrip("-").isdigit() and int(ms) > 0:
                    ranks.append({
                        "min_score": int(it.get("min", 0) or 0),
                        "min_rank": int(ms),
                        "batch": it.get("local_batch_name", ""),
                        "type": it.get("local_type_name", ""),
                    })
            except (ValueError, TypeError):
                continue
        if ranks:
            # 位次最小 = 录取要求最低
            best = min(ranks, key=lambda r: r["min_rank"])
            return year, best
        return year, None

    results = await asyncio.gather(*[_fetch_year(y) for y in years])
    return {y: r for y, r in results if r is not None}


async def fetch_school_full_info(
    school_name: str,
    province: str,
    years: Optional[list] = None,
) -> Optional[dict]:
    """高层接口: 给定院校名 + 考生省份, 返回完整数据

    Returns:
    {
        "school": {name, school_id, province, city, f985, f211, type, ...},
        "admission_ranks": {2024: {min_score, min_rank, batch, type}, 2023: {...}, 2022: {...}},
        "avg_min_rank": 26981,
        "confidence": 0.95,
        "source": "gaokao.cn API",
    }
    """
    school = await lookup_school_id(school_name)
    if not school:
        return None
    province_id = PROVINCE_ID_MAP.get(province)
    if not province_id:
        # 没有省份信息, 也返回学校基本信息
        return {
            "school": school,
            "admission_ranks": {},
            "avg_min_rank": None,
            "confidence": 0.5,
            "source": "gaokao.cn API (only school info, no province)",
        }
    ranks = await get_admission_ranks(school["school_id"], province_id, years)
    rank_values = [r["min_rank"] for r in ranks.values() if r.get("min_rank")]
    avg = int(sum(rank_values) / len(rank_values)) if rank_values else None
    return {
        "school": school,
        "admission_ranks": ranks,
        "avg_min_rank": avg,
        "confidence": 0.95 if ranks else 0.5,
        "source": "gaokao.cn API (掌上高考公共 API)",
    }


async def search_schools_by_name(keyword: str, limit: int = 10) -> list:
    """搜索院校 (按名字模糊匹配)
    Returns: [{school_id, name, province, city, f985, f211, type, ...}, ...]
    """
    if not keyword or len(keyword) < 2:
        return []
    data = await _get({
        "uri": "apidata/api/gkv3/school/lists",
        "keyword": keyword,
        "page": 1,
        "size": limit,
    })
    items = data.get("data", {}).get("item", [])
    return [_format_school(it) for it in items[:limit]]
