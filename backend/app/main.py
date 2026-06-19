from __future__ import annotations

import csv
import io
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

from .skills import process_with_skill, skill_catalog

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./murmur.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


class Murmur(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str
    transcript: str
    space: str = Field(index=True)
    source: str = "text"
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class MurmurCreate(BaseModel):
    transcript: str
    title: Optional[str] = None
    space: Optional[str] = None


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


app = FastAPI(title="Murmur API", version="0.3.0")
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


def save_murmur(transcript: str, source: str, space: Optional[str] = None, language: Optional[str] = None, duration: Optional[float] = None, title: Optional[str] = None) -> Murmur:
    murmur = Murmur(
        title=title or build_title(transcript),
        transcript=transcript,
        space=space or detect_space(transcript),
        source=source,
        language=language,
        duration_seconds=duration,
    )
    with Session(engine) as session:
        session.add(murmur)
        session.commit()
        session.refresh(murmur)
    return murmur


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)


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
def list_murmurs(space: Optional[str] = None, query: Optional[str] = None) -> list[Murmur]:
    with Session(engine) as session:
        rows = session.exec(select(Murmur).order_by(Murmur.created_at.desc())).all()
        if space and space != "All murmurs":
            rows = [row for row in rows if row.space.lower() == space.lower()]
        if query:
            q = query.lower()
            rows = [row for row in rows if q in row.title.lower() or q in row.transcript.lower()]
        return rows


@app.post("/api/murmurs", response_model=MurmurRead)
def create_murmur(payload: MurmurCreate) -> Murmur:
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript cannot be empty")
    return save_murmur(transcript, "text", payload.space, title=payload.title)


@app.delete("/api/murmurs/{murmur_id}", status_code=204)
def delete_murmur(murmur_id: str) -> Response:
    with Session(engine) as session:
        murmur = session.get(Murmur, murmur_id)
        if not murmur:
            raise HTTPException(status_code=404, detail="Murmur not found")
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


@app.get("/api/export.csv")
def export_csv() -> Response:
    with Session(engine) as session:
        rows = session.exec(select(Murmur).order_by(Murmur.created_at.desc())).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "transcript", "space", "source", "language", "duration_seconds", "created_at"])
    for row in rows:
        writer.writerow([row.id, row.title, row.transcript, row.space, row.source, row.language or "", row.duration_seconds or "", row.created_at.isoformat()])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=murmurs.csv"})


@app.post("/api/transcribe", response_model=MurmurRead)
async def transcribe_audio(audio: UploadFile = File(...), space: Optional[str] = Form(None)) -> Murmur:
    suffix = Path(audio.filename or "capture.webm").suffix or ".webm"
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

    try:
        model = get_model()
        segments, info = model.transcribe(temp_path, beam_size=5, vad_filter=True, vad_parameters={"min_silence_duration_ms": 450})
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech was detected")
        return save_murmur(
            transcript,
            "voice",
            space,
            getattr(info, "language", None),
            getattr(info, "duration", None),
        )
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
