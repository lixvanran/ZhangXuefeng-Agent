"""Database ORM models"""
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from app.core.config import settings

Base = declarative_base()


# ========== User (extended) ==========
class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    # 学历阶段：primary/middle/high/vocational/junior_college/bachelor/master/abroad/working/other
    education_stage = Column(String(32), default="high")
    # All optional now
    province = Column(String(32), nullable=True)
    score = Column(Integer, nullable=True)
    rank = Column(Integer, nullable=True)
    target = Column(String(128), nullable=True)
    interests = Column(Text, nullable=True)
    background = Column(Text, nullable=True)  # Free-form self-introduction
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ========== Conversation ==========
class ConversationORM(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    scenario = Column(String(32), default="chat")
    title = Column(String(128), default="New chat")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    messages = relationship(
        "MessageORM",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageORM.created_at",
    )


# ========== Message ==========
class MessageORM(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(16))  # user/assistant/system/tool
    content = Column(Text)
    tool_calls = Column(Text)  # JSON string
    created_at = Column(DateTime, default=datetime.now)

    conversation = relationship("ConversationORM", back_populates="messages")


# ========== Resource (unified: mistakes + materials) ==========
class ResourceORM(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    # 'mistake' = 错题 | 'material' = 学习资料
    type = Column(String(16), nullable=False, default="material")
    # Auto-generated code for RAG reference: M-001, S-001 etc.
    code = Column(String(16), nullable=True, index=True)
    # Common
    subject = Column(String(32), nullable=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=True)
    file_path = Column(String(512), nullable=True)
    tags = Column(JSON, nullable=True)  # List[str]
    # User notes / solution / thinking (for both mistake and material)
    notes = Column(Text, nullable=True)
    solution = Column(Text, nullable=True)
    thinking = Column(Text, nullable=True)
    # Mistake-only
    knowledge_point = Column(String(128), nullable=True)
    error_type = Column(String(32), nullable=True)  # calculation/concept/method/unfamiliar
    mastered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ========== Database setup ==========
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create tables and seed demo data. Handles simple schema migration."""
    _migrate_if_needed()
    Base.metadata.create_all(bind=engine)
    _seed_demo()


def _migrate_if_needed():
    """温和的列补全迁移 — 不再 DROP TABLE
    - 缺的列用 ALTER TABLE 补 (SQLite 支持)
    - 实在补不上的才提示手动处理
    """
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if 'resources' not in inspector.get_table_names():
        return  # 全新安装, 让 create_all 处理
    existing_cols = {c['name'] for c in inspector.get_columns('resources')}
    # 字段 → 默认值 / 类型
    new_cols = {
        'code':            ('VARCHAR(16)',  "''"),
        'notes':           ('TEXT',         "NULL"),
        'solution':        ('TEXT',         "NULL"),
        'thinking':        ('TEXT',         "NULL"),
        'mastered':        ('BOOLEAN',      "0"),
    }
    with engine.connect() as conn:
        for col, (ctype, default) in new_cols.items():
            if col not in existing_cols:
                logger.info(f"Schema migration: adding resources.{col}")
                try:
                    conn.execute(text(
                        f"ALTER TABLE resources ADD COLUMN {col} {ctype} DEFAULT {default}"
                    ))
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to add column {col}: {e}")
        # 索引补全 (code 列经常按它查)
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_resources_code ON resources (code)"))
            conn.commit()
        except Exception as e:
            logger.debug(f"Index ix_resources_code: {e}")


def _seed_demo():
    """Seed demo user"""
    db = SessionLocal()
    try:
        if not db.query(UserORM).first():
            demo = UserORM(
                id=1,
                name="Student",
                education_stage="high",
                province="",
                score=None,
                rank=None,
                target="",
                interests="",
                background="",
            )
            db.add(demo)
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
