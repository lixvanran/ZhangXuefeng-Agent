"""错题本工具 - v0.9.1 新增
- 扫描 workspace/uploads/ 目录
- 用 Vision 模型识别图片内容
- 调数据库 + RAG 写入错题本
- 用户在 Chat 里说"把上传文件夹里的错题整理一下" 即可触发
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.db.database import SessionLocal, ResourceORM
from app.services.resource_service import generate_code, build_rag_content
from app.agent.rag import rag_engine

logger = logging.getLogger(__name__)


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f}KB"
    return f"{n/1024/1024:.1f}MB"


async def wrong_book_scan_uploads() -> Dict:
    """扫描 workspace/uploads/ 目录, 列出所有待处理文件
    Returns:
        {
            "success": True,
            "uploads_dir": "...",
            "items": [{name, path, size, mtime, ext}],
            "total": N
        }
    """
    try:
        uploads = settings.WORKSPACE_UPLOADS_DIR
        uploads.mkdir(parents=True, exist_ok=True)

        items = []
        for p in sorted(uploads.iterdir()):
            if p.name.startswith("."):  # 跳过 .gitkeep 等
                continue
            if not p.is_file():
                continue
            stat = p.stat()
            items.append({
                "name": p.name,
                "path": f"uploads/{p.name}",  # 相对 workspace 的路径
                "absolute_path": str(p),
                "size": stat.st_size,
                "size_human": _format_size(stat.st_size),
                "mtime": stat.st_mtime,
                "ext": p.suffix.lower(),
            })
        return {
            "success": True,
            "uploads_dir": str(uploads),
            "items": items,
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"wrong_book_scan_uploads error: {e}")
        return {"success": False, "error": str(e)}


async def wrong_book_describe_file(file_path: str) -> Dict:
    """用 Vision 模型识别图片/PDF 文件内容, 提取错题信息

    Args:
        file_path: 相对 workspace 的路径, 如 'uploads/xxx.jpg'
                   或绝对路径
    Returns:
        {
            "success": True,
            "file": ...,
            "description": "...",  # Vision 模型的描述
            "model_used": "..."
        }
        或 success=False + error
    """
    # 解析路径
    if Path(file_path).is_absolute():
        p = Path(file_path)
    else:
        p = (settings.WORKSPACE_DIR / file_path).resolve()
        # 安全检查: 必须在 WORKSPACE_DIR 下
        if not str(p).startswith(str(settings.WORKSPACE_DIR.resolve())):
            return {"success": False, "error": f"非法路径: {file_path}"}

    if not p.exists() or not p.is_file():
        return {"success": False, "error": f"文件不存在: {file_path}"}

    ext = p.suffix.lower()
    # 图片走 Vision 模型
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        try:
            from app.agent.llm.vision import vision_client
            ok, desc, model = await vision_client.describe(str(p))
            if not ok:
                return {"success": False, "error": desc, "file": str(p)}
            return {
                "success": True,
                "file": str(p),
                "file_name": p.name,
                "description": desc,
                "model_used": model,
                "type": "image",
            }
        except Exception as e:
            logger.error(f"Vision error for {p}: {e}")
            return {"success": False, "error": f"识别失败: {e}", "file": str(p)}

    # 文本类文件直接读
    if ext in {".txt", ".md"}:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            return {
                "success": True,
                "file": str(p),
                "file_name": p.name,
                "description": content,
                "model_used": "direct_read",
                "type": "text",
            }
        except Exception as e:
            return {"success": False, "error": f"读文件失败: {e}"}

    # PDF/Word 暂不支持直接读, 提示用户
    return {
        "success": False,
        "error": f"暂不支持 {ext} 文件自动识别, 请转为图片或文本后重试",
        "file": str(p),
        "supported": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".txt", ".md"],
    }


async def wrong_book_add_mistake(
    title: str,
    content: str,
    file_path: Optional[str] = None,
    subject: str = "",
    knowledge_point: str = "",
    error_type: str = "",
    notes: str = "",
    user_id: int = 1,
) -> Dict:
    """把识别出的内容写入错题本

    Args:
        title: 错题标题 (必填, 简短描述)
        content: 错题内容/题目 (必填)
        file_path: 关联的文件路径 (可选)
        subject: 学科 (数学/语文/...)
        knowledge_point: 知识点 (圆锥曲线/函数/...)
        error_type: 错误类型 (计算错误/概念不清/...)
        notes: 备注
        user_id: 用户 ID
    Returns:
        {
            "success": True,
            "code": "M-001",  # 错题编号
            "id": 123,
            "rag_indexed": True/False
        }
    """
    if not title or not content:
        return {"success": False, "error": "title 和 content 必填"}

    db = SessionLocal()
    try:
        # 生成错题编号
        code = generate_code(db, user_id, "mistake")

        # v0.9.6: 存相对路径 (前端用 /uploads/xxx 访问)
        # 之前存绝对路径 (D:\xxx\uploads\xxx) 导致浏览器 404
        stored_file_path = file_path
        if file_path:
            # 转成相对路径 (uploads/xxx) 不管传进来的是相对/绝对
            p = Path(file_path)
            try:
                # 如果在 WORKSPACE_DIR 下, 转成相对路径
                rel = p.resolve().relative_to(settings.WORKSPACE_DIR.resolve())
                stored_file_path = str(rel).replace("\\", "/")
            except (ValueError, OSError):
                # 不在 workspace 下, 保留原样
                stored_file_path = str(p).replace("\\", "/")

        resource = ResourceORM(
            user_id=user_id,
            type="mistake",
            code=code,
            title=title,
            content=content,
            file_path=stored_file_path,
            subject=subject or None,
            knowledge_point=knowledge_point or None,
            error_type=error_type or None,
            notes=notes or None,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)

        # 入 RAG 索引
        rag_content = build_rag_content(resource)
        rag_ok = rag_engine.add_resource(
            resource.id,
            rag_content,
            metadata={
                "user_id": str(user_id),
                "type": "mistake",
                "code": code,
                "title": title,
                "subject": subject or "",
                "knowledge_point": knowledge_point or "",
            },
        )
        logger.info(f"Added wrong book {code}: {title} (RAG: {rag_ok})")

        return {
            "success": True,
            "code": code,
            "id": resource.id,
            "title": title,
            "subject": subject,
            "knowledge_point": knowledge_point,
            "rag_indexed": rag_ok,
            "message": f"已加入错题本: {code} {title}",
        }
    except Exception as e:
        logger.error(f"wrong_book_add_mistake error: {e}")
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def wrong_book_query(
    subject: Optional[str] = None,
    knowledge_point: Optional[str] = None,
    mastered: Optional[bool] = None,
    limit: int = 20,
    user_id: int = 1,
) -> Dict:
    """查询错题本

    Args:
        subject: 按学科过滤
        knowledge_point: 按知识点过滤 (模糊匹配)
        mastered: 是否已掌握 (True/False/None=全部)
        limit: 返回数量
        user_id: 用户 ID
    Returns:
        {
            "success": True,
            "items": [{code, title, subject, knowledge_point, ...}],
            "total": N
        }
    """
    db = SessionLocal()
    try:
        q = db.query(ResourceORM).filter_by(user_id=user_id, type="mistake")
        if subject:
            q = q.filter(ResourceORM.subject == subject)
        if knowledge_point:
            q = q.filter(ResourceORM.knowledge_point.like(f"%{knowledge_point}%"))
        if mastered is not None:
            q = q.filter(ResourceORM.mastered == mastered)
        items = q.order_by(ResourceORM.created_at.desc()).limit(limit).all()
        return {
            "success": True,
            "items": [
                {
                    "code": r.code,
                    "title": r.title,
                    "subject": r.subject,
                    "knowledge_point": r.knowledge_point,
                    "error_type": r.error_type,
                    "mastered": r.mastered,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in items
            ],
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"wrong_book_query error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()
