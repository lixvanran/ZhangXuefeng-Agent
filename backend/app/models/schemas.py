"""Pydantic models"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from enum import Enum


# ===== Enums =====
class ScenarioEnum(str, Enum):
    EXAM = "exam"
    VOLUNTEER = "volunteer"
    CHAT = "chat"


class EducationStageEnum(str, Enum):
    PRIMARY = "primary"          # 小学
    MIDDLE = "middle"            # 初中
    HIGH = "high"                # 高中
    VOCATIONAL = "vocational"    # 职高/中专
    JUNIOR_COLLEGE = "junior_college"  # 大专
    BACHELOR = "bachelor"        # 本科
    MASTER = "master"            # 考研/硕士
    ABROAD = "abroad"            # 留学
    WORKING = "working"          # 在职/工作
    OTHER = "other"


class ResourceTypeEnum(str, Enum):
    MISTAKE = "mistake"
    MATERIAL = "material"


class ErrorTypeEnum(str, Enum):
    CALCULATION = "calculation"
    CONCEPT = "concept"
    METHOD = "method"
    UNFAMILIAR = "unfamiliar"


# ===== User =====
class UserBase(BaseModel):
    name: str = "Student"
    education_stage: str = "high"
    province: Optional[str] = None
    score: Optional[int] = None
    rank: Optional[int] = None
    target: Optional[str] = None
    interests: Optional[str] = None
    background: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    education_stage: Optional[str] = None
    province: Optional[str] = None
    score: Optional[int] = None
    rank: Optional[int] = None
    target: Optional[str] = None
    interests: Optional[str] = None
    background: Optional[str] = None


class User(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== Chat =====
class ChatRequest(BaseModel):
    message: str
    scenario: ScenarioEnum = ScenarioEnum.CHAT
    conversation_id: Optional[int] = None
    user_id: int = 1
    stream: bool = True
    # Per-request feature toggles (None = use .env default)
    web_search_enabled: Optional[bool] = None
    deep_thinking_enabled: Optional[bool] = None
    # v0.7.5+: 强制指定模型档位 (low/medium/high) - 测试用, 跳过复杂度评估
    force_tier: Optional[str] = None


# ===== Conversation =====
class ConversationCreate(BaseModel):
    scenario: ScenarioEnum = ScenarioEnum.CHAT
    title: Optional[str] = None
    user_id: int = 1


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class Conversation(BaseModel):
    id: int
    user_id: int
    scenario: str
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Message(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    tool_calls: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationWithMessages(Conversation):
    messages: List[Message] = []


# ===== Resource (unified) =====
class ResourceCreate(BaseModel):
    type: ResourceTypeEnum = ResourceTypeEnum.MATERIAL
    subject: Optional[str] = None
    title: str
    content: Optional[str] = None
    tags: List[str] = []
    # Mistake-only
    knowledge_point: Optional[str] = None
    error_type: Optional[str] = None
    # User notes (work for both mistake and material)
    notes: Optional[str] = None
    solution: Optional[str] = None
    thinking: Optional[str] = None


class ResourceUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    subject: Optional[str] = None
    tags: Optional[List[str]] = None
    knowledge_point: Optional[str] = None
    error_type: Optional[str] = None
    mastered: Optional[bool] = None
    notes: Optional[str] = None
    solution: Optional[str] = None
    thinking: Optional[str] = None


class Resource(BaseModel):
    id: int
    user_id: int
    type: str
    code: Optional[str] = None
    title: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    subject: Optional[str] = None
    tags: List[str] = []
    knowledge_point: Optional[str] = None
    error_type: Optional[str] = None
    mastered: bool = False
    notes: Optional[str] = None
    solution: Optional[str] = None
    thinking: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ===== Search =====
class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    type: Optional[ResourceTypeEnum] = None


class SearchResult(BaseModel):
    id: int
    type: str
    title: str
    content: str
    subject: Optional[str] = None
    score: float  # similarity


# ===== Volunteer =====
class VolunteerRequest(BaseModel):
    user_id: int = 1
    score: int
    rank: int
    province: str
    subject_type: str = "理科"
    interests: Optional[str] = None
    preferences: Optional[dict] = None
