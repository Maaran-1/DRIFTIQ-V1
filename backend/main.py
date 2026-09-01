"""DRIFTIQ MVP — FastAPI backend v0.3.0
Features added:
  - Multilingual ASR: asr.transcribe() returns (text, detected_lang)
  - GET /api/analytics: lecture stats, top topics, classroom activity
  - /api/process: passes detected_lang back in response
"""
from __future__ import annotations
import time
import uuid
import logging
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
import asr
import audio_prep
import extract
import db
import models
import auth
import public

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("driftiq")

app = FastAPI(title="DRIFTIQ MVP", version="0.3.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.include_router(auth.router)
app.include_router(public.router)


@app.exception_handler(Exception)
async def unhandled_exception(request, exc):
    log.error("unhandled error on %s:\n%s", request.url.path, traceback.format_exc())
    return JSONResponse(status_code=500, content={"ok": False, "detail": str(exc) or "Internal server error"})


@app.on_event("startup")
async def init_db():
    if db.engine.dialect.name == "sqlite":
        async with db.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
    elif config.JWT_SECRET.startswith("driftiq-dev-only"):
        log.warning("JWT_SECRET is the dev default but database is not the local fallback.")


async def _persist_lecture(
    session: AsyncSession,
    *,
    user: models.User,
    subject: str,
    classroom: str | None,
    audio_path: str | None,
    transcript: str,
    bookmarks: list,
    notes: dict,
    markdown: str,
    asr_provider: str | None = None,
) -> tuple[int, int]:
    """Save a processed lecture + draft note (version 1). Returns (lecture_id, note_id)."""
    lecture = models.Lecture(
        user_id=user.id,
        subject=subject,
        classroom=classroom or None,
        audio_path=audio_path,
        transcript=transcript,
        moments=bookmarks,
        asr_provider=asr_provider or config.ASR_PROVIDER,
        llm_provider=config.LLM_PROVIDER,
    )
    session.add(lecture)
    await session.flush()
    note = models.Note(lecture_id=lecture.id, content=notes, markdown=markdown, status="draft")
    session.add(note)
    await session.flush()
    session.add(models.NoteVersion(note_id=note.id, version=1, content=notes, markdown=markdown))
    await session.commit()
    return lecture.id, note.id


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "asr_provider": config.ASR_PROVIDER,
        "llm_provider": config.LLM_PROVIDER,
    }


@app.post("/api/process")
async def process_audio(
    audio: UploadFile = File(...),
    moments: str = Form("[]"),
    subject: str = Form(""),
    classroom: str = Form(""),
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    """Full pipeline: audio → multilingual transcript → structured notes → persist."""
    import json as _json
    t0 = time.time()
    ext = Path(audio.filename or "audio.webm").suffix or ".webm"
    fp = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    asr_input = fp
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    try:
        size = 0
        with fp.open("wb") as out:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Audio exceeds the {config.MAX_UPLOAD_MB} MB limit.",
                    )
                out.write(chunk)
        log.info(f"received {size/1024:.1f} KB → {fp}")

        try:
            bookmarks = _json.loads(moments or "[]")
            if not isinstance(bookmarks, list): bookmarks = []
        except Exception:
            bookmarks = []

        t1 = time.time()
        try:
            asr_input = audio_prep.transcode_for_asr(fp)
            log.info(f"transcoded {fp.stat().st_size/1e6:.1f} MB → {asr_input.stat().st_size/1e6:.1f} MB in {time.time()-t1:.1f}s")
        except Exception as te:
            log.warning(f"transcode failed ({te}); using original upload")
            asr_input = fp

        subject_clean = subject.strip()
        initial_prompt = subject_clean or ""

        t1 = time.time()
        # asr.transcribe now returns (transcript, detected_language)
        transcript, detected_lang = asr.transcribe(str(asr_input), initial_prompt=initial_prompt)
        t2 = time.time()
        log.info(f"transcribed in {t2-t1:.1f}s: {len(transcript)} chars, lang={detected_lang}")

        notes = extract.extract_notes(transcript, moments=bookmarks)
        t3 = time.time()
        log.info(f"extracted in {t3-t2:.1f}s")

        markdown = extract.notes_to_markdown(notes)

        lecture_id, note_id = await _persist_lecture(
            session,
            user=user,
            subject=subject_clean or notes.get("subject") or "Unknown",
            classroom=classroom.strip(),
            audio_path=audio.filename,
            transcript=transcript,
            bookmarks=bookmarks,
            notes=notes,
            markdown=markdown,
        )
        log.info(f"persisted lecture={lecture_id} note={note_id} (draft), lang={detected_lang}")

        return {
            "ok": True,
            "lecture_id": lecture_id,
            "note_id": note_id,
            "transcript": transcript,
            "notes": notes,
            "markdown": markdown,
            "detected_lang": detected_lang,
            "detected_lang_name": asr.LANG_NAMES.get(detected_lang, detected_lang.upper()),
            "timing": {
                "transcribe_s": round(t2 - t1, 2),
                "extract_s":    round(t3 - t2, 2),
                "total_s":      round(time.time() - t0, 2),
            },
            "providers": {
                "asr": config.ASR_PROVIDER,
                "llm": config.LLM_PROVIDER,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("process failed:\n" + traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        fp.unlink(missing_ok=True)
        if asr_input != fp:
            asr_input.unlink(missing_ok=True)


@app.post("/api/extract")
async def extract_only(
    transcript: str = Form(...),
    subject: str = Form(""),
    classroom: str = Form(""),
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    """Skip ASR — text transcript → notes → persisted (full parity with audio)."""
    try:
        t0 = time.time()
        notes = extract.extract_notes(transcript)
        t1 = time.time()
        markdown = extract.notes_to_markdown(notes)
        subject_clean = subject.strip() or notes.get("subject") or "Unknown"

        lecture_id, note_id = await _persist_lecture(
            session,
            user=user,
            subject=subject_clean,
            classroom=classroom.strip(),
            audio_path=None,
            transcript=transcript,
            bookmarks=[],
            notes=notes,
            markdown=markdown,
            asr_provider="text",
        )
        log.info(f"persisted text-extracted lecture={lecture_id} note={note_id}")

        return {
            "ok": True,
            "lecture_id": lecture_id,
            "note_id": note_id,
            "transcript": transcript,
            "notes": notes,
            "markdown": markdown,
            "detected_lang": "text",
            "detected_lang_name": "Text Input",
            "timing": {"extract_s": round(t1 - t0, 2), "total_s": round(time.time() - t0, 2)},
            "providers": {"asr": "text", "llm": config.LLM_PROVIDER},
        }
    except Exception as e:
        log.error("extract failed:\n" + traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/lectures")
async def list_lectures(
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    result = await session.execute(
        select(models.Lecture, models.Note)
        .outerjoin(models.Note, models.Note.lecture_id == models.Lecture.id)
        .where(models.Lecture.user_id == user.id)
        .order_by(models.Lecture.created_at.desc(), models.Lecture.id.desc())
    )
    lectures = []
    for lecture, note in result.all():
        lectures.append({
            "id": lecture.id,
            "subject": lecture.subject,
            "classroom": lecture.classroom,
            "created_at": lecture.created_at.isoformat() if lecture.created_at else None,
            "transcript_chars": len(lecture.transcript or ""),
            "bookmarks": len(lecture.moments or []),
            "asr_provider": lecture.asr_provider,
            "note": {
                "id": note.id,
                "status": note.status,
                "slug": note.slug,
            } if note else None,
        })
    return {"ok": True, "lectures": lectures}


@app.get("/api/lectures/{lecture_id}")
async def get_lecture(
    lecture_id: int,
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    row = (
        await session.execute(
            select(models.Lecture, models.Note)
            .outerjoin(models.Note, models.Note.lecture_id == models.Lecture.id)
            .where(models.Lecture.id == lecture_id, models.Lecture.user_id == user.id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture, note = row
    return {
        "ok": True,
        "lecture": {
            "id": lecture.id,
            "subject": lecture.subject,
            "classroom": lecture.classroom,
            "created_at": lecture.created_at.isoformat() if lecture.created_at else None,
            "transcript": lecture.transcript,
            "moments": lecture.moments or [],
            "asr_provider": lecture.asr_provider,
            "llm_provider": lecture.llm_provider,
        },
        "note": {
            "id": note.id,
            "status": note.status,
            "slug": note.slug,
            "markdown": note.markdown,
            "content": note.content,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        } if note else None,
    }


async def _owned_note(note_id: int, session: AsyncSession, user: models.User) -> models.Note:
    note = (
        await session.execute(
            select(models.Note)
            .join(models.Lecture, models.Lecture.id == models.Note.lecture_id)
            .where(models.Note.id == note_id, models.Lecture.user_id == user.id)
        )
    ).scalar_one_or_none()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


class NoteEdit(BaseModel):
    markdown: str


@app.put("/api/notes/{note_id}")
async def update_note(
    note_id: int,
    body: NoteEdit,
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    note = await _owned_note(note_id, session, user)
    max_version = (
        await session.execute(
            select(sa_func.max(models.NoteVersion.version)).where(models.NoteVersion.note_id == note.id)
        )
    ).scalar() or 0
    note.markdown = body.markdown
    session.add(models.NoteVersion(note_id=note.id, version=max_version + 1, content=note.content, markdown=body.markdown))
    await session.commit()
    return {"ok": True, "note_id": note.id, "version": max_version + 1}


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60] or "lecture"


@app.post("/api/notes/{note_id}/publish")
async def publish_note(
    note_id: int,
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    note = await _owned_note(note_id, session, user)
    if note.slug is None:
        lecture = await session.get(models.Lecture, note.lecture_id)
        date_part = lecture.created_at.date().isoformat() if lecture.created_at else ""
        note.slug = f"{_slugify(lecture.subject)}-{date_part}-{uuid.uuid4().hex[:6]}"
    note.status = "published"
    await session.commit()
    return {"ok": True, "note_id": note.id, "slug": note.slug, "url": f"/notes/{note.slug}"}


@app.post("/api/notes/{note_id}/unpublish")
async def unpublish_note(
    note_id: int,
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    note = await _owned_note(note_id, session, user)
    note.status = "draft"
    await session.commit()
    return {"ok": True, "note_id": note.id, "status": "draft"}


@app.get("/api/classroom-topics")
async def classroom_topics(
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    """Aggregate topic coverage grouped by classroom."""
    result = await session.execute(
        select(models.Lecture, models.Note)
        .outerjoin(models.Note, models.Note.lecture_id == models.Lecture.id)
        .where(models.Lecture.user_id == user.id)
        .order_by(models.Lecture.classroom.asc(), models.Lecture.created_at.asc())
    )
    classrooms: dict[str, list] = {}
    for lecture, note in result.all():
        name = lecture.classroom or "Unassigned"
        if name not in classrooms:
            classrooms[name] = []
        topics = []
        if note and note.content:
            topics = [t.get("title","").strip() for t in (note.content.get("topics") or []) if t.get("title","").strip()]
        classrooms[name].append({
            "lecture_id": lecture.id,
            "subject": lecture.subject,
            "date": lecture.created_at.isoformat() if lecture.created_at else None,
            "topics": topics,
            "note_status": note.status if note else None,
            "note_id": note.id if note else None,
        })
    return {
        "ok": True,
        "classrooms": [
            {"name": n, "total_topics": sum(len(s["topics"]) for s in ss), "sessions": ss}
            for n, ss in classrooms.items()
        ],
    }


@app.get("/api/analytics")
async def analytics(
    session: AsyncSession = Depends(db.get_session),
    user: models.User = Depends(auth.get_current_user),
):
    """
    Lecture analytics for the current user:
    - Total lectures, published count, lectures this week
    - Classroom activity breakdown
    - Top 10 topics by frequency across all lectures
    - Subject diversity count
    """
    # Total lectures
    total_lectures = (await session.execute(
        select(sa_func.count()).select_from(models.Lecture).where(models.Lecture.user_id == user.id)
    )).scalar() or 0

    # Published notes count
    published_count = (await session.execute(
        select(sa_func.count()).select_from(models.Note)
        .join(models.Lecture, models.Lecture.id == models.Note.lecture_id)
        .where(models.Lecture.user_id == user.id, models.Note.status == "published")
    )).scalar() or 0

    # Lectures in the last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_count = (await session.execute(
        select(sa_func.count()).select_from(models.Lecture)
        .where(models.Lecture.user_id == user.id, models.Lecture.created_at >= week_ago)
    )).scalar() or 0

    # Classroom breakdown
    classroom_rows = (await session.execute(
        select(models.Lecture.classroom, sa_func.count().label("cnt"))
        .where(models.Lecture.user_id == user.id)
        .group_by(models.Lecture.classroom)
        .order_by(sa_func.count().desc())
    )).all()
    classrooms = [{"name": r[0] or "Unassigned", "count": r[1]} for r in classroom_rows]

    # Subject breakdown
    subject_rows = (await session.execute(
        select(models.Lecture.subject, sa_func.count().label("cnt"))
        .where(models.Lecture.user_id == user.id)
        .group_by(models.Lecture.subject)
        .order_by(sa_func.count().desc())
    )).all()
    subjects = [{"name": r[0] or "Unknown", "count": r[1]} for r in subject_rows]

    # Top topics from note content JSON
    all_notes = (await session.execute(
        select(models.Note)
        .join(models.Lecture, models.Lecture.id == models.Note.lecture_id)
        .where(models.Lecture.user_id == user.id)
    )).scalars().all()

    topic_counter: dict[str, int] = {}
    for note in all_notes:
        if note.content:
            for t in (note.content.get("topics") or []):
                title = (t.get("title") or "").strip()
                if title:
                    topic_counter[title] = topic_counter.get(title, 0) + 1

    top_topics = sorted(topic_counter.items(), key=lambda x: x[1], reverse=True)[:10]

    # Total recording hours estimate (rough: avg 1000 chars/minute transcription rate)
    total_chars = (await session.execute(
        select(sa_func.sum(sa_func.length(models.Lecture.transcript)))
        .where(models.Lecture.user_id == user.id)
    )).scalar() or 0
    est_minutes = round(total_chars / 1000)

    return {
        "ok": True,
        "total_lectures": total_lectures,
        "published_count": published_count,
        "recent_count_7d": recent_count,
        "total_unique_topics": len(topic_counter),
        "est_minutes_recorded": est_minutes,
        "classrooms": classrooms,
        "subjects": subjects,
        "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
    }


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    print(config.summary())
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
