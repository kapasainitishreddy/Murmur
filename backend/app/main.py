from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .portability import BackupValidationError, build_backup, safe_csv_cell, validate_backup
from .schema_migration import migrate_murmur_table
from .skills import process_with_skill, skill_catalog
from .upload_policy import AudioUploadError, choose_audio_suffix

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./murmur.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))
MAX_TAGS = 32
MAX_TAG_LENGTH = 64

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Murmur(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    transcript: str
    space: str = Field(index=True)
    source: str = "text"
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=now_utc, index=True)
    updated_at: datetime = Field(default_factory=now_utc, index=True)
    tags_json: str = "[]"
    pinned: bool = Field(default=False, index=True)


class MurmurCreate(BaseModel):
    transcript: str
    title: Optional[str] = None
    space: Optional[str] = None
    tags: list[str] = PydanticField(default_factory=list)
    pinned: bool = False


class MurmurUpdate(BaseModel):
    title: Optional[str] = None
    transcript: Optional[str] = None
    space: Optional[str] = None
    tags: Optional[list[str]] = None
    pinned: Optional[bool] = None


class MurmurRestore(BaseModel):
    backup: dict[str, Any]
    mode: str = "replace"


class MurmurProcess(BaseModel):
    transcript: str
    skill: Optional[str] = None


class MurmurRead(BaseModel):
    id: str
    title: str
    transcript: str
    space: str
    source: str
    language: Optional[str]
    duration_seconds: Optional[float]
    created_at: datetime
    updated_at: datetime
    tags: list[str] = PydanticField(default_factory=list)
    pinned: bool = False


app = FastAPI(title="Murmur API", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_model = None


def get_model():
    global _model
    if WhisperModel is None:
        raise HTTPException(status_code=503, detail="faster-whisper is not installed correctly")
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    return _model


def detect_space(text: str) -> str:
    value = text.lower()
    rules = [
        ("Bug report", ("bug", "error", "freeze", "broken", "crash", "button", "issue")),
        ("Records", ("contractor", "apartment", "damage", "inspection", "warranty", "agreed")),
        ("Care", ("pet", "dog", "cat", "vet", "medicine", "pain", "doctor")),
        ("Work", ("task", "client", "project", "inventory", "follow up", "work", "sop")),
    ]
    for space, keywords in rules:
        if any(keyword in value for keyword in keywords):
            return space
    return "Memory"


def build_title(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return "Untitled murmur"
    return cleaned if len(cleaned) <= 64 else f"{cleaned[:61]}..."


def normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = raw.strip()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise HTTPException(status_code=422, detail=f"Tags may be at most {MAX_TAG_LENGTH} characters")
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
        if len(normalized) > MAX_TAGS:
            raise HTTPException(status_code=422, detail=f"A murmur may have at most {MAX_TAGS} tags")
    return normalized


def serialize_tags(tags: list[str]) -> str:
    return json.dumps(normalize_tags(tags), ensure_ascii=False, separators=(",", ":"))


def deserialize_tags(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        return []
    return value[:MAX_TAGS]


def murmur_read(murmur: Murmur) -> dict[str, Any]:
    return {
        "id": murmur.id,
        "title": murmur.title,
        "transcript": murmur.transcript,
        "space": murmur.space,
        "source": murmur.source,
        "language": murmur.language,
        "duration_seconds": murmur.duration_seconds,
        "created_at": murmur.created_at,
        "updated_at": murmur.updated_at,
        "tags": deserialize_tags(murmur.tags_json),
        "pinned": murmur.pinned,
    }


def save_murmur(
    transcript: str,
    source: str,
    space: Optional[str] = None,
    language: Optional[str] = None,
    duration: Optional[float] = None,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
    pinned: bool = False,
) -> Murmur:
    instant = now_utc()
    murmur = Murmur(
        title=title or build_title(transcript),
        transcript=transcript,
        space=space or detect_space(transcript),
        source=source,
        language=language,
        duration_seconds=duration,
        created_at=instant,
        updated_at=instant,
        tags_json=serialize_tags(tags or []),
        pinned=pinned,
    )
    with Session(engine) as session:
        session.add(murmur)
        session.commit()
        session.refresh(murmur)
    return murmur


def murmur_to_backup_record(murmur: Murmur) -> dict[str, Any]:
    return {
        "id": murmur.id,
        "title": murmur.title,
        "transcript": murmur.transcript,
        "space": murmur.space,
        "source": murmur.source,
        "language": murmur.language,
        "duration_seconds": murmur.duration_seconds,
        "created_at": murmur.created_at.isoformat(),
        "updated_at": murmur.updated_at.isoformat(),
        "tags": deserialize_tags(murmur.tags_json),
        "pinned": murmur.pinned,
    }


def parse_backup_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)
    migrate_murmur_table(engine)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "transcription": "faster-whisper",
        "model": WHISPER_MODEL,
        "database": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres",
        "skills": len(skill_catalog()),
    }


@app.get("/api/skills")
def list_skills() -> list[dict[str, str]]:
    return skill_catalog()


@app.post("/api/process")
def process_murmur(payload: MurmurProcess) -> dict[str, Any]:
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript cannot be empty")
    return process_with_skill(transcript, payload.skill)


@app.get("/api/murmurs", response_model=list[MurmurRead])
def list_murmurs(space: Optional[str] = None, query: Optional[str] = None) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(select(Murmur)).all()
    rows.sort(key=lambda row: (bool(row.pinned), row.created_at), reverse=True)
    if space and space != "All murmurs":
        rows = [row for row in rows if row.space.lower() == space.lower()]
    if query:
        q = query.lower()
        rows = [
            row
            for row in rows
            if q in row.title.lower()
            or q in row.transcript.lower()
            or q in row.space.lower()
            or any(q in tag.lower() for tag in deserialize_tags(row.tags_json))
        ]
    return [murmur_read(row) for row in rows]


@app.post("/api/murmurs", response_model=MurmurRead)
def create_murmur(payload: MurmurCreate) -> dict[str, Any]:
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript cannot be empty")
    title = payload.title.strip() if payload.title is not None else None
    if payload.title is not None and not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    space = payload.space.strip() if payload.space is not None else None
    if payload.space is not None and not space:
        raise HTTPException(status_code=422, detail="Space cannot be empty")
    murmur = save_murmur(
        transcript,
        "text",
        space,
        title=title,
        tags=payload.tags,
        pinned=payload.pinned,
    )
    return murmur_read(murmur)


@app.patch("/api/murmurs/{murmur_id}", response_model=MurmurRead)
def update_murmur(murmur_id: str, payload: MurmurUpdate) -> dict[str, Any]:
    if (
        payload.title is None
        and payload.transcript is None
        and payload.space is None
        and payload.tags is None
        and payload.pinned is None
    ):
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    with Session(engine) as session:
        murmur = session.get(Murmur, murmur_id)
        if not murmur:
            raise HTTPException(status_code=404, detail="Murmur not found")

        if payload.title is not None:
            title = payload.title.strip()
            if not title:
                raise HTTPException(status_code=422, detail="Title cannot be empty")
            murmur.title = title
        if payload.transcript is not None:
            transcript = payload.transcript.strip()
            if not transcript:
                raise HTTPException(status_code=422, detail="Transcript cannot be empty")
            murmur.transcript = transcript
        if payload.space is not None:
            space = payload.space.strip()
            if not space:
                raise HTTPException(status_code=422, detail="Space cannot be empty")
            murmur.space = space
        if payload.tags is not None:
            murmur.tags_json = serialize_tags(payload.tags)
        if payload.pinned is not None:
            murmur.pinned = payload.pinned
        murmur.updated_at = now_utc()

        session.add(murmur)
        session.commit()
        session.refresh(murmur)
        return murmur_read(murmur)


@app.delete("/api/murmurs/{murmur_id}", status_code=204)
def delete_murmur(murmur_id: str) -> Response:
    with Session(engine) as session:
        murmur = session.get(Murmur, murmur_id)
        if not murmur:
            raise HTTPException(status_code=404, detail="Murmur not found")
        session.delete(murmur)
        session.commit()
    return Response(status_code=204)


@app.delete("/api/murmurs", status_code=204)
def erase_all_murmurs() -> Response:
    with Session(engine) as session:
        for murmur in session.exec(select(Murmur)).all():
            session.delete(murmur)
        session.commit()
    return Response(status_code=204)


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with Session(engine) as session:
        rows = session.exec(select(Murmur)).all()
    by_space: dict[str, int] = {}
    voice_seconds = 0.0
    for row in rows:
        by_space[row.space] = by_space.get(row.space, 0) + 1
        voice_seconds += row.duration_seconds or 0
    return {"total": len(rows), "by_space": by_space, "voice_minutes": round(voice_seconds / 60, 1)}


@app.get("/api/export.json")
def export_json() -> dict[str, Any]:
    with Session(engine) as session:
        rows = session.exec(select(Murmur)).all()
    rows.sort(key=lambda row: (bool(row.pinned), row.created_at), reverse=True)
    return build_backup([murmur_to_backup_record(row) for row in rows])


@app.post("/api/restore")
def restore_backup(payload: MurmurRestore) -> dict[str, Any]:
    try:
        normalized = validate_backup(payload.backup)
    except BackupValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    mode = payload.mode.strip().lower()
    if mode not in {"replace", "merge"}:
        raise HTTPException(status_code=422, detail="Restore mode must be replace or merge")

    restored = 0
    skipped = 0
    with Session(engine) as session:
        existing = session.exec(select(Murmur)).all()
        existing_ids = {row.id for row in existing}

        if mode == "replace":
            for row in existing:
                session.delete(row)
            existing_ids.clear()

        for record in normalized["records"]:
            if record["id"] in existing_ids:
                skipped += 1
                continue
            session.add(
                Murmur(
                    id=record["id"],
                    title=record["title"].strip(),
                    transcript=record["transcript"].strip(),
                    space=record["space"].strip(),
                    source=record["source"].strip(),
                    language=record.get("language"),
                    duration_seconds=record.get("duration_seconds"),
                    created_at=parse_backup_timestamp(record["created_at"]),
                    updated_at=parse_backup_timestamp(record["updated_at"]),
                    tags_json=serialize_tags(record.get("tags", [])),
                    pinned=record.get("pinned", False),
                )
            )
            existing_ids.add(record["id"])
            restored += 1

        session.commit()

    return {"mode": mode, "restored": restored, "skipped": skipped}


@app.get("/api/export.csv")
def export_csv() -> Response:
    with Session(engine) as session:
        rows = session.exec(select(Murmur)).all()
    rows.sort(key=lambda row: (bool(row.pinned), row.created_at), reverse=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "title",
        "transcript",
        "space",
        "source",
        "language",
        "duration_seconds",
        "created_at",
        "updated_at",
        "tags",
        "pinned",
    ])
    for row in rows:
        writer.writerow([
            safe_csv_cell(row.id),
            safe_csv_cell(row.title),
            safe_csv_cell(row.transcript),
            safe_csv_cell(row.space),
            safe_csv_cell(row.source),
            safe_csv_cell(row.language or ""),
            row.duration_seconds or "",
            row.created_at.isoformat(),
            row.updated_at.isoformat(),
            safe_csv_cell("; ".join(deserialize_tags(row.tags_json))),
            "true" if row.pinned else "false",
        ])
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=murmurs.csv"},
    )


@app.post("/api/transcribe", response_model=MurmurRead)
async def transcribe_audio(audio: UploadFile = File(...), space: Optional[str] = Form(None)) -> dict[str, Any]:
    try:
        suffix = choose_audio_suffix(audio.content_type or "", audio.filename)
    except AudioUploadError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        total = 0
        while chunk := await audio.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_MB * 1024 * 1024:
                temp.close()
                os.unlink(temp.name)
                raise HTTPException(status_code=413, detail="Audio file is too large")
            temp.write(chunk)
        temp_path = temp.name

    if total == 0:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise HTTPException(status_code=422, detail="Audio file is empty")

    try:
        model = get_model()
        segments, info = model.transcribe(
            temp_path,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 450},
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech was detected")
        murmur = save_murmur(
            transcript,
            "voice",
            space,
            getattr(info, "language", None),
            getattr(info, "duration", None),
        )
        return murmur_read(murmur)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
