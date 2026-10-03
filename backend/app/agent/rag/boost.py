"""实体 boost - 识别查询中的省份+年份, 直接命中 gaokao_2026
v0.7.9.6 加的, 解决'老师/今年/今年高考'等通用 token 误匹配 life_kb 的问题
"""
from typing import List, Dict, Any, Optional


PROVINCE_NAMES = [
    "北京", "上海", "天津", "重庆", "河北", "山西", "内蒙古", "辽宁",
    "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西", "海南", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
]

YEAR_SIGNALS = [
    "2026", "2025", "今年", "去年", "前年",
    "今年高考", "分数线", "一本线", "本科线", "特控线",
    "特殊类型", "投档线", "录取线", "位次", "一分一段",
]


def detect_province(query: str) -> Optional[str]:
    """从 query 找出第一个出现的省份"""
    for p in PROVINCE_NAMES:
        if p in query:
            return p
    return None


def detect_year_signal(query: str) -> bool:
    """是否含年份/分数线信号"""
    return any(s in query for s in YEAR_SIGNALS)


def build_gaokao_boost_entry(item: Dict[str, Any], province: str) -> Dict[str, Any]:
    """把录取分单条数据格式化成 LLM 友好的文本, 带 score=100 强行置顶

    v0.10.0 修: 原实现是照着"武汉一校一投档线"的扁平字段硬编码的
    (投档线_WSL_武大_物理_普通 / 650分_物理_位次 / ...), 那些字段属于早已不存在的
    gaokao_2026 库。现在真正在用的是 08_admission_scores
    (school_name/min_score/avg_score/min_rank/batch/subject_type)。
    改为: 先渲染当前库真实拥有的字段, 再回落到通用字段渲染,
    避免对着一堆不存在的 key 输出 "本科线：物理 None / 历史 None"。
    """
    lines = [f"省份：{item.get('province', province)}"]

    # --- 旧 gaokao_2026 形态(保留兼容) ---
    legacy_pairs = (
        ("本科线", "本科_物理", "本科_历史"),
        ("特控线", "特殊类型_物理", "特殊类型_历史"),
    )
    for label, phys, hist in legacy_pairs:
        if item.get(phys) or item.get(hist):
            lines.append(f"{label}：物理 {item.get(phys, '-')} / 历史 {item.get(hist, '-')}")
    for key, label in (
        ("总考生_万", "总考生：{v} 万人"),
        ("本科上线_总计", "本科上线总人数：{v}"),
        ("600分以上_总人数", "600分以上：{v} 人"),
        ("投档线_WSL_武大_物理_普通", "武大物理投档线：{v}"),
        ("投档线_HUST_华科_物理_普通", "华科物理投档线：{v}"),
        ("投档线_WUT_武汉理工_物理_普通", "武汉理工物理投档线：{v}"),
        ("投档线_HBUT_湖北工业_AI", "湖北工业AI投档区间：{v}"),
        ("650分_物理_位次", "650分物理对应位次：{v}"),
        ("650分_能上", "650分能上：{v}"),
        ("official_source", "数据来源：{v}"),
    ):
        if item.get(key):
            lines.append(label.format(v=item[key]))

    # --- 08_admission_scores 形态(当前在用) ---
    if item.get("school_name"):
        head = f"院校：{item['school_name']}"
        for f, lbl in (("year", "年份"), ("batch", "批次"), ("subject_type", "科类")):
            if item.get(f):
                head += f" | {lbl}: {item[f]}"
        lines.append(head)
    scores = []
    for f, lbl in (("min_score", "最低分"), ("avg_score", "平均分"),
                   ("max_score", "最高分"), ("min_rank", "最低位次")):
        if item.get(f) is not None:
            scores.append(f"{lbl}: {item[f]}")
    if scores:
        lines.append(" | ".join(scores))

    if item.get("张老师点评"):
        lines.append(f"\n张老师点评：{item['张老师点评']}")

    year = item.get("year") or 2026
    return {
        "type": "gaokao_2026",
        "title": f"{province} {year} 高考分数线",
        "content": "\n".join(lines),
        "score": 100,  # boost: 永远排第一
        "province": province,   # v0.10.0: 顶层也带 province, 方便调用方直接判定
        "data": item,
    }


def maybe_apply_boost(query: str, knowledge_base) -> List[Dict[str, Any]]:
    """如果 query 含省份+年份信号, 返回 boost 后的结果集（只用 1 条, 强行置顶）

    v0.10.0 修: 之前硬编码找 `"gaokao_2026"` 这个 key, 但 v0.8.0 把 KB 重做成
    `01_*/02_*/...08_admission_scores` 之后该库已不存在 → 这个函数**永远 return []**,
    实体置顶是彻底的死代码。现改为按候选名依次探测, 兼容新旧库名,
    并支持传入 KBRegistry(用 .get() 而非 `in`)。
    """
    province = detect_province(query)
    has_year_signal = detect_year_signal(query)
    if not (province and has_year_signal):
        return []
    src = _resolve_scores_source(knowledge_base)
    if src is None:
        return []
    for item in src:
        if isinstance(item, dict) and item.get("province") == province:
            return [build_gaokao_boost_entry(item, province)]
    return []


def _resolve_scores_source(knowledge_base):
    """拿到录取分库的条目列表 — 兼容 dict(旧) 与 KBRegistry(新)

    判定要点: 别去探测容器类型 —— 普通 dict 也有 .get, 而 KBRegistry 本身
    并不带 KBSource 的 index_of。正确做法是取出来之后看**值**是不是 KBSource。
    """
    candidates = ("08_admission_scores", "gaokao_2026", "admission_scores")

    def _as_kbs_source(obj):
        """是 KBSource 就返回, 否则 None"""
        if obj is None or isinstance(obj, (list, dict)):
            return None
        if hasattr(obj, "index_of") and hasattr(obj, "items"):
            return obj
        return None

    getter = getattr(knowledge_base, "get", None)
    if callable(getter):
        for name in candidates:
            kbs = _as_kbs_source(getter(name))
            if kbs is not None and isinstance(getattr(kbs, "items", None), list):
                return kbs.items

    if isinstance(knowledge_base, dict):
        for name in candidates:
            val = knowledge_base.get(name)
            if isinstance(val, list):
                return val
    return None
