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
    """把 gaokao_2026 单条数据格式化成 LLM 友好的文本, 带 score=100 强行置顶"""
    rich_lines = [
        f"省份：{item.get('province')}",
        f"本科线：物理 {item.get('本科_物理')} / 历史 {item.get('本科_历史')}",
        f"特控线：物理 {item.get('特殊类型_物理')} / 历史 {item.get('特殊类型_历史')}",
    ]
    if item.get('总考生_万'):
        rich_lines.append(f"总考生：{item.get('总考生_万')} 万人")
    if item.get('本科上线_总计'):
        rich_lines.append(f"本科上线总人数：{item.get('本科上线_总计')}")
    if item.get('600分以上_总人数'):
        rich_lines.append(f"600分以上：{item.get('600分以上_总人数')} 人")
    if item.get('投档线_WSL_武大_物理_普通'):
        rich_lines.append(f"武大物理投档线：{item.get('投档线_WSL_武大_物理_普通')}")
    if item.get('投档线_HUST_华科_物理_普通'):
        rich_lines.append(f"华科物理投档线：{item.get('投档线_HUST_华科_物理_普通')}")
    if item.get('投档线_WUT_武汉理工_物理_普通'):
        rich_lines.append(f"武汉理工物理投档线：{item.get('投档线_WUT_武汉理工_物理_普通')}")
    if item.get('投档线_HBUT_湖北工业_AI'):
        rich_lines.append(f"湖北工业AI投档区间：{item.get('投档线_HBUT_湖北工业_AI')}")
    if item.get('650分_物理_位次'):
        rich_lines.append(f"650分物理对应位次：{item.get('650分_物理_位次')}")
    if item.get('650分_能上'):
        rich_lines.append(f"650分能上：{item.get('650分_能上')}")
    if item.get('official_source'):
        rich_lines.append(f"数据来源：{item.get('official_source')}")
    rich_lines.append(f"\n张老师点评：{item.get('张老师点评', '')}")
    return {
        "type": "gaokao_2026",
        "title": f"{province} 2026 高考分数线",
        "content": "\n".join(rich_lines),
        "score": 100,  # boost: 永远排第一
        "data": item,
    }


def maybe_apply_boost(query: str, knowledge_base: Dict) -> List[Dict[str, Any]]:
    """如果 query 含省份+年份信号, 返回 boost 后的结果集（只用 1 条, 强行置顶）"""
    province = detect_province(query)
    has_year_signal = detect_year_signal(query)
    if not (province and has_year_signal):
        return []
    if "gaokao_2026" not in knowledge_base:
        return []
    for item in knowledge_base["gaokao_2026"]:
        if isinstance(item, dict) and item.get("province") == province:
            return [build_gaokao_boost_entry(item, province)]
    return []
