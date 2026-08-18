"""Tool 注册表 - 统一调度所有工具
LLM 通过 tool_calls 调 execute_tool(name, args)
"""
import logging
from typing import Dict, Callable, Awaitable

from app.agent.tools.college import query_college
from app.agent.tools.major import analyze_major
from app.agent.tools.admission import (
    calculate_admission_probability,
    calculate_match,            # v0.8.0
    search_policy,              # v0.8.0 升级
    compare_schools,            # v0.8.0
    search_school,              # v0.9.0 新增 — 接 db/schools.json + v0.9.8 接入掌上高考 API
    search_major,               # v0.9.0 新增 — 接 db/majors.json
    query_school_admission,     # v0.9.8 新增 — 掌上高考 API 查录取位次
)
from app.agent.tools.web import search_web, fetch_url
from app.agent.tools.workspace import (
    workspace_list, workspace_read, workspace_write,
    workspace_search, workspace_delete, workspace_info,
)
from app.agent.tools.wrong_book import (
    wrong_book_scan_uploads,         # v0.9.1 新增
    wrong_book_describe_file,        # v0.9.1 新增
    wrong_book_add_mistake,          # v0.9.1 新增
    wrong_book_query,                # v0.9.1 新增
)

logger = logging.getLogger(__name__)


# 工具注册表: name -> async function
# v0.9.0: 全面接 db/ 大数据 (8.5万条录取分 / 3765所院校 / 585个专业)
TOOL_REGISTRY: Dict[str, Callable[..., Awaitable[Dict]]] = {
    "query_college": query_college,
    "analyze_major": analyze_major,
    "calculate_admission_probability": calculate_admission_probability,
    "calculate_match": calculate_match,        # 冲稳保推荐 — 接 db/scores.json
    "compare_schools": compare_schools,        # 多院校对比 — 接 db/schools.json
    "search_school": search_school,            # v0.9.0 新增 — 院校搜索 (v0.9.8 优先掌上高考 API)
    "search_major": search_major,              # v0.9.0 新增 — 专业搜索
    "query_school_admission": query_school_admission,  # v0.9.8 新增 — 查录取位次 (掌上高考 API)
    "search_policy": search_policy,            # 政策库
    "search_web": search_web,
    "fetch_url": fetch_url,
    # ===== workspace 文件夹操作 =====
    "workspace_list": workspace_list,
    "workspace_read": workspace_read,
    # v0.9.6: read_file 工具 stub — LLM 幻觉调 read_file 时也能工作
    # 等效 workspace_read, 但对 uploads/ 下的图片会走 Vision 识别
    "read_file": workspace_read,
    "workspace_write": workspace_write,
    "workspace_search": workspace_search,
    "workspace_delete": workspace_delete,
    "workspace_info": workspace_info,
    # ===== v0.9.1 错题本工具 =====
    "wrong_book_scan_uploads": wrong_book_scan_uploads,
    "wrong_book_describe_file": wrong_book_describe_file,
    "wrong_book_add_mistake": wrong_book_add_mistake,
    "wrong_book_query": wrong_book_query,
}


async def execute_tool(tool_name: str, arguments: Dict) -> Dict:
    """执行一个工具调用
    Returns: 工具结果 dict, 失败时返回 {"error": str}
    """
    tool_func = TOOL_REGISTRY.get(tool_name)
    if not tool_func:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return await tool_func(**arguments)
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return {"error": str(e)}
