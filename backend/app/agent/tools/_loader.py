"""Tools 内部共用 - 加载知识库 JSON + db JSON
- knowledge_base/: LLM RAG 用的结构化知识 (语录/策略/政策/院校精选)
- db/: 大数据事实表 (8.5万条录取分/3765所院校/585个专业) — 工具直接查
"""
import json
from pathlib import Path
from typing import Any

# 项目 backend 根
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
KNOWLEDGE_DIR = BACKEND_ROOT / "knowledge_base"
DB_DIR = BACKEND_ROOT / "db"


def load_json(filename: str) -> Any:
    """兼容旧接口: 优先 knowledge_base, 不存在再 db"""
    fp = KNOWLEDGE_DIR / filename
    if not fp.exists():
        fp = DB_DIR / filename
    if not fp.exists():
        return []
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def load_kb(filename: str) -> Any:
    """加载 knowledge_base/ 下的文件"""
    fp = KNOWLEDGE_DIR / filename
    if not fp.exists():
        return []
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db(filename: str) -> Any:
    """加载 db/ 下的文件 (大数据事实表)"""
    fp = DB_DIR / filename
    if not fp.exists():
        return []
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)
