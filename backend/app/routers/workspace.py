"""Workspace API - 用户文件上传到 workspace/uploads/
v0.9.1: 新增 - 用户把错题图片/PDF/Word 等文件传到 uploads/,
        然后在聊天里指示 Agent 自动归类到错题本
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pathlib import Path
import uuid
import aiofiles
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["工作区"])


# 支持的文件类型
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
                      ".pdf", ".doc", ".docx", ".txt", ".md"}


@router.post("/upload")
async def upload_to_workspace(
    file: UploadFile = File(...),
    user_id: int = Form(1),
):
    """把文件上传到 workspace/uploads/ 目录

    用户在 Chat 页面通过 📎 按钮选文件, 或直接从桌面拖到 workspace/uploads/
    之后在聊天里说"把上传文件夹里的错题整理一下", Agent 会自动识别并归类
    """
    try:
        # 文件名校验
        if not file.filename:
            raise HTTPException(400, "文件名为空")

        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                400,
                f"不支持的文件类型: {ext}。允许: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # 生成唯一文件名 (保留原扩展名, 避免冲突)
        safe_stem = Path(file.filename).stem[:50]  # 限长
        unique_name = f"{safe_stem}_{uuid.uuid4().hex[:8]}{ext}"
        dest = settings.WORKSPACE_UPLOADS_DIR / unique_name

        # 写入
        content_bytes = await file.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content_bytes)

        logger.info(f"Workspace upload: {file.filename} -> {dest} ({len(content_bytes)} bytes)")

        return {
            "success": True,
            "filename": unique_name,
            "original_name": file.filename,
            "path": f"uploads/{unique_name}",
            "absolute_path": str(dest),
            "size": len(content_bytes),
            "message": f"已上传到 workspace/uploads/{unique_name}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace upload error: {e}")
        raise HTTPException(500, f"上传失败: {str(e)}")


@router.get("/uploads")
async def list_uploads():
    """列出 workspace/uploads/ 目录里的所有文件 (Agent 和前端都看)

    返回未处理文件列表, 供 Agent 扫描
    """
    try:
        uploads_dir = settings.WORKSPACE_UPLOADS_DIR
        if not uploads_dir.exists():
            return {"success": True, "items": [], "total": 0}

        items = []
        for p in sorted(uploads_dir.iterdir()):
            if p.name.startswith("."):
                continue  # 跳过 .gitkeep 等
            stat = p.stat()
            items.append({
                "name": p.name,
                "path": f"uploads/{p.name}",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
        return {"success": True, "items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"List uploads error: {e}")
        return {"success": False, "error": str(e)}
