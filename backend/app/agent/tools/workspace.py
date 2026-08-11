"""Workspace 工具 - agent 对项目主目录下的 workspace/ 文件夹进行操作
v0.8.0: 让 agent 读/写/列/搜用户工作文件夹, 像 Claude Code 那样
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _safe_resolve(path: str) -> Optional[Path]:
    """安全解析路径, 防止 ../ 跳出 workspace"""
    workspace = settings.WORKSPACE_DIR.resolve()
    try:
        p = (workspace / path).resolve()
        # 必须在 workspace 下
        if not str(p).startswith(str(workspace)):
            return None
        return p
    except Exception:
        return None


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f}KB"
    return f"{n/1024/1024:.1f}MB"


async def workspace_list(path: str = ".", pattern: str = "*") -> Dict:
    """列出 workspace/ 下的文件
    Args:
        path: 相对路径 (默认 "." = workspace 根)
        pattern: glob 模式 (默认 "*" = 全部, 可以是 "*.md", "错题本/*" 等)
    Returns:
        {"success": True, "path": ..., "items": [{name, type, size, mtime}], "total": N}
    """
    try:
        base = _safe_resolve(path)
        if base is None:
            return {"success": False, "error": f"非法路径: {path}"}
        if not base.exists():
            return {"success": False, "error": f"目录不存在: {path}"}
        if not base.is_dir():
            return {"success": False, "error": f"不是目录: {path}"}
        # 列出
        items = []
        # 先目录, 后文件
        dirs = sorted([p for p in base.iterdir() if p.is_dir() and not p.name.startswith('.')])
        files = sorted([p for p in base.iterdir() if p.is_file() and not p.name.startswith('.')])
        for p in dirs:
            if pattern != "*" and not p.match(pattern):
                continue
            stat = p.stat()
            items.append({
                "name": p.name + "/",
                "type": "dir",
                "size": None,
                "size_human": "-",
                "mtime": stat.st_mtime,
            })
        for p in files:
            if pattern != "*" and not p.match(pattern):
                continue
            stat = p.stat()
            items.append({
                "name": p.name,
                "type": "file",
                "size": stat.st_size,
                "size_human": _format_size(stat.st_size),
                "mtime": stat.st_mtime,
            })
        return {
            "success": True,
            "path": str(path),
            "absolute_path": str(base),
            "items": items,
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"workspace_list error: {e}")
        return {"success": False, "error": str(e)}


async def workspace_read(path: str, max_chars: int = 50000, start_line: int = 0) -> Dict:
    """读 workspace/ 下的文件
    Args:
        path: 相对路径
        max_chars: 最大字符数 (默认 50000, 防止 LLM 拿到超大文件)
        start_line: 从第几行开始读 (默认 0)
    Returns:
        {"success": True, "path": ..., "content": ..., "truncated": bool, "total_lines": N, "size": N}
    """
    try:
        p = _safe_resolve(path)
        if p is None:
            return {"success": False, "error": f"非法路径: {path}"}
        if not p.exists():
            return {"success": False, "error": f"文件不存在: {path}"}
        if not p.is_file():
            return {"success": False, "error": f"不是文件: {path}"}
        # 二进制直接拒绝
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"success": False, "error": f"不是文本文件 (二进制?): {path}"}
        total_lines = content.count("\n") + 1
        # 截行
        lines = content.split("\n")
        if start_line > 0:
            lines = lines[start_line:]
        content = "\n".join(lines)
        # 截字符
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars] + f"\n\n[...截断, 原文还有 {len(content) - max_chars} 字符, {total_lines} 行...]"
        return {
            "success": True,
            "path": str(path),
            "absolute_path": str(p),
            "content": content,
            "truncated": truncated,
            "total_lines": total_lines,
            "size": p.stat().st_size,
        }
    except Exception as e:
        logger.error(f"workspace_read error: {e}")
        return {"success": False, "error": str(e)}


async def workspace_write(path: str, content: str, mode: str = "overwrite") -> Dict:
    """写 workspace/ 下的文件
    Args:
        path: 相对路径 (会自动创建父目录)
        content: 文件内容
        mode: "overwrite" (覆盖) 或 "append" (追加)
    Returns:
        {"success": True, "path": ..., "size": N, "mode": ...}
    """
    try:
        p = _safe_resolve(path)
        if p is None:
            return {"success": False, "error": f"非法路径: {path}"}
        # 自动创建父目录
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with p.open("a", encoding="utf-8") as f:
                written = f.write(content)
        else:
            with p.open("w", encoding="utf-8") as f:
                written = f.write(content)
        return {
            "success": True,
            "path": str(path),
            "absolute_path": str(p),
            "size": p.stat().st_size,
            "written_bytes": written,
            "mode": mode,
        }
    except Exception as e:
        logger.error(f"workspace_write error: {e}")
        return {"success": False, "error": str(e)}


async def workspace_search(query: str, path: str = ".", max_results: int = 20, file_pattern: str = "*") -> Dict:
    """在 workspace/ 下搜文件内容
    Args:
        query: 关键词 (会做大小写不敏感的中文匹配)
        path: 搜索的根目录 (默认 "." = 全部)
        max_results: 最多返回多少个匹配项
        file_pattern: 文件名 glob 模式 (默认 "*", 可以是 "*.md")
    Returns:
        {"success": True, "query": ..., "matches": [{file, line, content}], "total": N}
    """
    try:
        base = _safe_resolve(path)
        if base is None:
            return {"success": False, "error": f"非法路径: {path}"}
        if not base.exists():
            return {"success": False, "error": f"目录不存在: {path}"}
        matches = []
        # 递归搜
        for fp in base.rglob("*"):
            if not fp.is_file():
                continue
            if not fp.match(file_pattern):
                continue
            # 跳过二进制
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            # 按行匹配
            for i, line in enumerate(content.split("\n"), 1):
                if query.lower() in line.lower():
                    rel_path = str(fp.relative_to(base))
                    matches.append({
                        "file": rel_path,
                        "line": i,
                        "content": line[:300],  # 单行截 300 字
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
        return {
            "success": True,
            "query": query,
            "path": str(path),
            "matches": matches,
            "total": len(matches),
            "truncated": len(matches) >= max_results,
        }
    except Exception as e:
        logger.error(f"workspace_search error: {e}")
        return {"success": False, "error": str(e)}


async def workspace_delete(path: str) -> Dict:
    """删除 workspace/ 下的文件或空目录
    注意: 不递归删除非空目录, 安全
    """
    try:
        p = _safe_resolve(path)
        if p is None:
            return {"success": False, "error": f"非法路径: {path}"}
        if not p.exists():
            return {"success": False, "error": f"文件不存在: {path}"}
        if p.is_dir():
            # 检查是否为空
            if any(p.iterdir()):
                return {"success": False, "error": f"目录非空, 不递归删除: {path}"}
            p.rmdir()
        else:
            p.unlink()
        return {
            "success": True,
            "path": str(path),
            "absolute_path": str(p),
        }
    except Exception as e:
        logger.error(f"workspace_delete error: {e}")
        return {"success": False, "error": str(e)}


async def workspace_info() -> Dict:
    """workspace/ 整体信息 (给 LLM 一开始就看到)
    Returns:
        {"success": True, "path": ..., "total_files": N, "total_size_human": ..., "tree": [...]}
    """
    try:
        ws = settings.WORKSPACE_DIR
        total_files = 0
        total_size = 0
        for fp in ws.rglob("*"):
            if fp.is_file():
                total_files += 1
                total_size += fp.stat().st_size
        # 列根目录
        root_items = await workspace_list(".")
        return {
            "success": True,
            "path": str(ws),
            "total_files": total_files,
            "total_size": total_size,
            "total_size_human": _format_size(total_size),
            "root_items": root_items.get("items", [])[:20],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
