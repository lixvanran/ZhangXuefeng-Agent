"""Resource service: auto-generate codes, build RAG content."""
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.database import ResourceORM


def generate_code(db: Session, user_id: int, resource_type: str) -> str:
    """Auto-generate a user-friendly code for a new resource.
    M-001, M-002 for mistakes; S-001, S-002 for materials.
    Counter is per (user_id, type).
    """
    prefix = "M" if resource_type == "mistake" else "S"
    count = db.query(func.count(ResourceORM.id)).filter_by(
        user_id=user_id, type=resource_type
    ).scalar() or 0
    return f"{prefix}-{count + 1:03d}"


def build_rag_content(resource: ResourceORM) -> str:
    """Format a resource as text for RAG indexing."""
    code = resource.code or f"ID{resource.id}"
    label = "错题" if resource.type == "mistake" else "学习资料"
    parts = [
        f"[{label} {code}] {resource.title}",
        f"类型: {resource.type}",
    ]
    if resource.subject:
        parts.append(f"学科: {resource.subject}")
    if resource.knowledge_point:
        parts.append(f"知识点: {resource.knowledge_point}")
    if resource.error_type:
        parts.append(f"错误类型: {resource.error_type}")
    if resource.content:
        parts.append(f"内容: {resource.content}")
    if resource.notes:
        parts.append(f"备注: {resource.notes}")
    if resource.solution:
        parts.append(f"解法: {resource.solution}")
    if resource.thinking:
        parts.append(f"思路: {resource.thinking}")
    if resource.tags:
        parts.append(f"标签: {', '.join(resource.tags)}")
    return "\n".join(parts)
