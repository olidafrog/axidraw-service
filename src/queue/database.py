"""Database models for job queue"""
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Column, String, Integer, DateTime, Text, Index, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from src.config import settings

Base = declarative_base()


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime"""
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    """Job status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """Job database model"""
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    status = Column(String, nullable=False, default=JobStatus.QUEUED.value, index=True)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    parameters = Column(Text, nullable=True)  # JSON string
    
    # Composite index for common query pattern (queued jobs ordered by creation time)
    __table_args__ = (
        Index('ix_jobs_status_created_at', 'status', 'created_at'),
    )


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

# Create async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """Initialize database (create tables)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
