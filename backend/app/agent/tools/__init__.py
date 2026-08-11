"""Tools 模块 - LLM 可调用的工具集
- registry.py: 工具注册表 + execute_tool 入口
- college.py: 查大学 (query_college)
- major.py: 查专业 (analyze_major)
- admission.py: 概率 + 政策 (calculate_admission_probability / search_policy)
- web.py: 联网搜索 + 抓全文 (search_web / fetch_url)
"""
from app.agent.tools.registry import TOOL_REGISTRY, execute_tool

__all__ = ["TOOL_REGISTRY", "execute_tool"]
