"""DRIFTIQ — Database models.
users → lectures → notes → notes_versions.
Notes land as drafts; nothing reaches students without an explicit Publish
(human-in-the-loop, see CLAUDE.md §4).
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Nullable until real auth lands (Week 1 task 2) — the placeholder
    # pilot user has no password.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    lectures: Mapped[list["Lecture"]] = relationship(back_populates="user")


class Lecture(Base):
    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(255), default="Unknown")
    classroom: Mapped[Optional[str]] = mapped_column(String(255))
    audio_path: Mapped[Optional[str]] = mapped_column(String(1024))
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    # Professor "mark this moment" bookmarks: [{t: seconds, label: str}]
    moments: Mapped[list] = mapped_column(JSON, default=list)
    asr_provider: Mapped[Optional[str]] = mapped_column(String(50))
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="lectures")
    note: Mapped[Optional["Note"]] = relationship(back_populates="lecture")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lecture_id: Mapped[int] = mapped_column(
        ForeignKey("lectures.id"), unique=True, index=True
    )
    # Structured notes JSON per extract.SYSTEM_PROMPT schema
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    # Public URL slug for /notes/<slug>; assigned on publish
    slug: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lecture: Mapped["Lecture"] = relationship(back_populates="note")
    versions: Mapped[list["NoteVersion"]] = relationship(
        back_populates="note", order_by="NoteVersion.version"
    )


class NoteVersion(Base):
    __tablename__ = "notes_versions"
    __table_args__ = (UniqueConstraint("note_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    markdown: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    note: Mapped["Note"] = relationship(back_populates="versions")
