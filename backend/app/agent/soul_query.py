"""灵魂追问 (Soul Query) — v0.9.0 借鉴参考项目
只针对志愿填报场景: 4 必问 (分数/省/科/家庭) + 3 选问 (城市/风险/职业)
- 第一问就是"你孩子考了多少分？"
- 不超过 5 轮
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List

MAX_QUERY_ROUNDS = 5

# 必问 4 项 (张雪峰风格话术)
REQUIRED_QUESTIONS: Dict[str, List[str]] = {
    "score": [
        "你孩子考了多少分？先把这个告诉我。",
        "高考成绩出来了吗？多少分？别磨叽，直接说。",
        "分数多少？这是最基础的，我得先知道这个才能给你建议。",
    ],
    "province": [
        "哪个省的？这个很重要，不同省差别太大了。",
        "孩子在哪儿参加的高考？省份不一样，策略完全不一样。",
    ],
    "subject_type": [
        "文科还是理科？新高考的话选的哪几科？",
        "孩子是文科生还是理科生？新高考省份告诉我选科组合。",
    ],
    "family_background": [
        "家里什么条件？工薪还是做生意的？这个决定完全不同的策略。",
        "家庭经济情况怎么样？普通工薪还是做生意？这个很重要。",
    ],
}

# 选问 3 项
OPTIONAL_QUESTIONS: Dict[str, List[str]] = {
    "target_city": [
        "有没有特别想去的城市？北上广深还是其他？",
    ],
    "risk_tolerance": [
        "你家是想稳一点还是可以冲一冲？保守选还是激进选？",
    ],
    "career_goal": [
        "孩子以后想干什么？有没有明确的职业方向？",
    ],
}

# 跳过时的默认值
SKIP_DEFAULTS: Dict[str, str] = {
    "target_city": "不限",
    "risk_tolerance": "稳健",
    "career_goal": "未确定",
}

REQUIRED_FIELDS = list(REQUIRED_QUESTIONS.keys())
OPTIONAL_FIELDS = list(OPTIONAL_QUESTIONS.keys())


@dataclass
class UserProfile:
    """用户画像 (简化版, 不上 Redis, 用 SQLite/文件)"""
    score: Optional[int] = None
    province: Optional[str] = None
    subject_type: Optional[str] = None  # 物理类/历史类/理科/文科
    family_background: Optional[str] = None  # 工薪/经商/困难
    target_city: Optional[str] = None
    risk_tolerance: Optional[str] = None  # 保守/稳健/激进
    career_goal: Optional[str] = None

    def missing_required(self) -> List[str]:
        return [f for f in REQUIRED_FIELDS if getattr(self, f, None) is None]

    def is_required_complete(self) -> bool:
        return len(self.missing_required()) == 0

    def to_context_dict(self) -> Dict[str, str]:
        out = {}
        if self.score: out["分数"] = self.score
        if self.province: out["省份"] = self.province
        if self.subject_type: out["科类"] = self.subject_type
        if self.family_background: out["家庭条件"] = self.family_background
        if self.target_city: out["目标城市"] = self.target_city
        if self.risk_tolerance: out["风险偏好"] = self.risk_tolerance
        if self.career_goal: out["职业方向"] = self.career_goal
        return out


@dataclass
class QueryState:
    round_count: int = 0
    asked_fields: List[str] = field(default_factory=list)
    skipped_fields: List[str] = field(default_factory=list)


class SoulQueryEngine:
    """灵魂追问引擎"""

    def get_next_question(self, profile: UserProfile, state: QueryState) -> Optional[str]:
        if state.round_count >= MAX_QUERY_ROUNDS:
            return None

        # 1) 必问字段优先
        for f in profile.missing_required():
            if f not in state.asked_fields:
                q = self._pick_q(f, state.round_count)
                state.asked_fields.append(f)
                state.round_count += 1
                return q

        # 2) 选问字段 (最多 1 个)
        for f in OPTIONAL_FIELDS:
            v = getattr(profile, f, None)
            if v is None and f not in state.asked_fields and f not in state.skipped_fields:
                q = self._pick_opt(f)
                state.asked_fields.append(f)
                state.round_count += 1
                return q

        return None

    def handle_skip(self, state: QueryState, field: str):
        if field not in state.skipped_fields:
            state.skipped_fields.append(field)

    def is_query_complete(self, profile: UserProfile) -> bool:
        return profile.is_required_complete()

    def _pick_q(self, field: str, rc: int) -> str:
        qs = REQUIRED_QUESTIONS.get(field, [])
        if not qs:
            return f"请告诉我你的{field}"
        return qs[rc % len(qs)]

    def _pick_opt(self, field: str) -> str:
        qs = OPTIONAL_QUESTIONS.get(field, [])
        return qs[0] if qs else f"方便的话告诉我你的{field}"


# =================================================================
# 字段提取 (从用户消息中识别: 分数/省/科类/家庭...)
# =================================================================

import re

def extract_profile_from_text(text: str, profile: UserProfile) -> UserProfile:
    """从用户消息中提取画像字段 (轻量 NLP)"""
    updated = profile

    # 1. 分数: "580分" "考了600" "分数是 580" "580 分"
    if updated.score is None:
        m = re.search(r'(\d{3,4})\s*分', text)
        if not m:
            m = re.search(r'考了\s*(\d{3,4})', text)
        if not m:
            m = re.search(r'分数[是为]?\s*(\d{3,4})', text)
        if m:
            score = int(m.group(1))
            if 300 <= score <= 750:
                updated.score = score

    # 2. 省份
    if updated.province is None:
        provinces = ["北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
                     "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
                     "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
                     "内蒙古", "广西", "西藏", "宁夏", "新疆"]
        for p in provinces:
            if p in text:
                updated.province = p
                break

    # 3. 科类
    if updated.subject_type is None:
        if "物理类" in text or "物理" in text and "历史" not in text:
            updated.subject_type = "物理类"
        elif "历史类" in text or ("文科" in text and "理科" not in text):
            updated.subject_type = "历史类"
        elif "理科" in text:
            updated.subject_type = "理科"
        elif "文科" in text:
            updated.subject_type = "文科"
        elif "新高考" in text:
            # 简单处理
            updated.subject_type = "综合"

    # 4. 家庭背景
    if updated.family_background is None:
        if any(w in text for w in ["做生意的", "经商", "家里有钱", "土豪", "富", "开公司的"]):
            updated.family_background = "经商"
        elif any(w in text for w in ["贫困", "困难", "农村", "脱贫", "专项"]):
            updated.family_background = "困难"
        elif any(w in text for w in ["工薪", "普通家庭", "一般", "小康"]):
            updated.family_background = "工薪"
        elif "中产" in text:
            updated.family_background = "中产"

    # 5. 目标城市 (选问)
    if updated.target_city is None:
        cities = ["北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "苏州"]
        for c in cities:
            if f"想去{c}" in text or f"去{c}" in text or f"留{c}" in text:
                updated.target_city = c
                break

    # 6. 风险偏好 (选问)
    if updated.risk_tolerance is None:
        if any(w in text for w in ["冲一冲", "敢冲", "激进"]):
            updated.risk_tolerance = "激进"
        elif any(w in text for w in ["保守", "稳", "求稳"]):
            updated.risk_tolerance = "保守"

    # 7. 职业方向 (选问)
    if updated.career_goal is None:
        if any(w in text for w in ["考公", "考编", "体制内", "公务员"]):
            updated.career_goal = "考公考编"
        elif any(w in text for w in ["当老师", "师范"]):
            updated.career_goal = "教师"
        elif any(w in text for w in ["当医生", "医学"]):
            updated.career_goal = "医生"
        elif any(w in text for w in ["程序员", "码农", "互联网", "IT"]):
            updated.career_goal = "互联网"

    return updated
