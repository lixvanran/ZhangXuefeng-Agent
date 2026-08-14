"""Resources API (mistakes + materials) with auto-codes and RAG integration."""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db, ResourceORM
from app.core.config import settings
from app.agent.rag import rag_engine
from app.services.resource_service import generate_code, build_rag_content
import os
import uuid
import aiofiles
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resources", tags=["资料库"])


def _serialize(r: ResourceORM) -> dict:
    # v0.9.6: file_path 转成 web URL
    # 后端可能存的是绝对路径 (老数据) 或相对路径 (新数据), 统一转成 /uploads/xxx
    file_url = None
    if r.file_path:
        from pathlib import Path as _P
        p = _P(r.file_path)
        # 取 basename, 加 /uploads/ 前缀
        if p.is_absolute():
            # 绝对路径: 提取 basename
            file_url = f"/uploads/{p.name}"
        else:
            # 相对路径: uploads/xxx.png → /uploads/xxx.png
            # 已经是 /uploads/xxx 形式则直接用
            if r.file_path.startswith("/uploads/"):
                file_url = r.file_path
            else:
                file_url = f"/uploads/{_P(r.file_path).name}"
    return {
        "id": r.id,
        "code": r.code,
        "type": r.type,
        "title": r.title,
        "content": r.content,
        "file_path": file_url or r.file_path,  # 优先用 web URL, 兜底用原值
        "subject": r.subject,
        "tags": r.tags or [],
        "knowledge_point": r.knowledge_point,
        "error_type": r.error_type,
        "mastered": r.mastered,
        "notes": r.notes,
        "solution": r.solution,
        "thinking": r.thinking,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/stats")
async def get_stats(user_id: int = 1, db: Session = Depends(get_db)):
    items = db.query(ResourceORM).filter_by(user_id=user_id).all()
    by_type = {}
    by_subject = {}
    mastered_count = 0
    for r in items:
        by_type[r.type] = by_type.get(r.type, 0) + 1
        if r.subject:
            by_subject[r.subject] = by_subject.get(r.subject, 0) + 1
        if r.mastered:
            mastered_count += 1
    return {
        "total": len(items),
        "by_type": by_type,
        "by_subject": by_subject,
        "mastered": mastered_count,
    }


@router.get("/list")
async def list_resources(
    user_id: int = 1,
    type: str = None,
    subject: str = None,
    search: str = None,
    db: Session = Depends(get_db),
):
    q = db.query(ResourceORM).filter_by(user_id=user_id)
    if type:
        q = q.filter(ResourceORM.type == type)
    if subject:
        q = q.filter(ResourceORM.subject == subject)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (ResourceORM.title.like(like)) |
            (ResourceORM.content.like(like)) |
            (ResourceORM.knowledge_point.like(like)) |
            (ResourceORM.notes.like(like))
        )
    items = q.order_by(ResourceORM.created_at.desc()).all()
    return {"total": len(items), "items": [_serialize(r) for r in items]}


@router.get("/{resource_id}")
async def get_resource(resource_id: int, db: Session = Depends(get_db)):
    """Get full resource detail (for view page)"""
    r = db.query(ResourceORM).filter_by(id=resource_id).first()
    if not r:
        raise HTTPException(404, "Resource not found")
    return _serialize(r)


@router.post("/create")
async def create_resource(
    type: str = Form("material"),
    title: str = Form(...),
    content: str = Form(""),
    subject: str = Form(""),
    tags: str = Form("[]"),
    knowledge_point: str = Form(""),
    error_type: str = Form(""),
    notes: str = Form(""),
    solution: str = Form(""),
    thinking: str = Form(""),
    user_id: int = Form(1),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    """Create a new resource (auto-generates code)"""
    file_path = None
    if file:
        ext = os.path.splitext(file.filename)[1] if file.filename else ""
        filename = f"{uuid.uuid4()}{ext}"
        filepath = settings.UPLOAD_DIR / filename
        async with aiofiles.open(filepath, "wb") as f:
            content_bytes = await file.read()
            await f.write(content_bytes)
        file_path = f"/uploads/{filename}"

    try:
        tags_list = json.loads(tags) if tags else []
    except Exception:
        tags_list = []

    # Auto-generate code
    code = generate_code(db, user_id, type)

    resource = ResourceORM(
        user_id=user_id,
        type=type,
        code=code,
        title=title,
        content=content or None,
        file_path=file_path,
        subject=subject or None,
        tags=tags_list,
        knowledge_point=knowledge_point or None,
        error_type=error_type or None,
        notes=notes or None,
        solution=solution or None,
        thinking=thinking or None,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    # Index in RAG
    rag_content = build_rag_content(resource)
    rag_ok = rag_engine.add_resource(
        resource.id,
        rag_content,
        metadata={
            "user_id": str(user_id),
            "type": type,
            "code": code,
            "title": title,
            "subject": subject or "",
            "knowledge_point": knowledge_point or "",
            "file_path": file_path or "",
        },
    )
    logger.info(f"Created {code} (RAG indexed: {rag_ok})")

    return {
        "id": resource.id,
        "code": code,
        "message": f"Created {code}",
        "rag_indexed": rag_ok,
    }


@router.post("/{resource_id}/update")
async def update_resource(
    resource_id: int,
    title: str = Form(None),
    content: str = Form(None),
    subject: str = Form(None),
    tags: str = Form(None),
    knowledge_point: str = Form(None),
    error_type: str = Form(None),
    mastered: str = Form(None),
    notes: str = Form(None),
    solution: str = Form(None),
    thinking: str = Form(None),
    db: Session = Depends(get_db),
):
    """Update a resource (any field)"""
    resource = db.query(ResourceORM).filter_by(id=resource_id).first()
    if not resource:
        raise HTTPException(404, "Not found")

    if title is not None: resource.title = title
    if content is not None: resource.content = content or None
    if subject is not None: resource.subject = subject or None
    if tags is not None:
        try: resource.tags = json.loads(tags) if tags else []
        except Exception: pass
    if knowledge_point is not None: resource.knowledge_point = knowledge_point or None
    if error_type is not None: resource.error_type = error_type or None
    if mastered is not None: resource.mastered = mastered.lower() == "true" if isinstance(mastered, str) else bool(mastered)
    if notes is not None: resource.notes = notes or None
    if solution is not None: resource.solution = solution or None
    if thinking is not None: resource.thinking = thinking or None

    db.commit()
    db.refresh(resource)

    # Re-index in RAG
    rag_content = build_rag_content(resource)
    rag_engine.update_resource(
        resource.id,
        rag_content,
        metadata={
            "user_id": str(resource.user_id),
            "type": resource.type,
            "code": resource.code or "",
            "title": resource.title,
            "subject": resource.subject or "",
            "knowledge_point": resource.knowledge_point or "",
        },
    )
    return {"message": "Updated", "id": resource_id}


@router.post("/{resource_id}/master")
async def mark_mastered(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(ResourceORM).filter_by(id=resource_id).first()
    if not resource:
        raise HTTPException(404, "Not found")
    resource.mastered = True
    db.commit()
    return {"message": "Marked mastered"}


@router.delete("/{resource_id}")
async def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(ResourceORM).filter_by(id=resource_id).first()
    if not resource:
        raise HTTPException(404, "Not found")
    if resource.file_path:
        try:
            fp = settings.UPLOAD_DIR / os.path.basename(resource.file_path)
            if fp.exists():
                fp.unlink()
        except Exception:
            pass
    db.delete(resource)
    db.commit()
    rag_engine.delete_resource(resource_id)
    return {"message": "Deleted"}


@router.post("/search")
async def search_resources(query: str, top_k: int = 5, type: str = None, user_id: int = 1):
    """Semantic search user's resources"""
    results = rag_engine.search_user_resources(query, user_id, top_k=top_k, resource_type=type)
    return {"query": query, "results": results}
