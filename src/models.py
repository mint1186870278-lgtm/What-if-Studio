"""SQLAlchemy ORM models"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from src.db import Base


class Project(Base):
    """Video editing project"""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    prompt = Column(Text, nullable=True)
    style_preference = Column(String(50), default="auto", nullable=False)
    script = Column(Text, nullable=True)
    product = Column(String(512), nullable=True)
    discussion_history = Column(JSON, default=list, nullable=False)
    discussion_status = Column(String(50), default="idle", nullable=False)
    last_opened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_ = Column(JSON, default=dict, nullable=False)  # Custom fields

    assets = relationship("Asset", back_populates="project", cascade="all, delete-orphan")


class Asset(Base):
    """Project asset (video, audio, image, text)"""

    __tablename__ = "assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    file_type = Column(String(50), nullable=False)  # 'video', 'audio', 'image', 'text'
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False, unique=True)
    file_size = Column(Integer, nullable=False)  # bytes
    metadata_ = Column(JSON, default=dict, nullable=False)  # resolution, duration, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="assets")

    @property
    def asset_type(self) -> str:
        return self.file_type

    @property
    def url(self) -> str:
        normalized = str(self.file_path or "").replace("\\", "/")
        return f"/storage/projects/{normalized}"

