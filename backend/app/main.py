from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select

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


class MurmurRead(BaseModel):
    id: str
    title: str
    transcript: str
    space: str
    source: str
    language: Optional[str]
    duration_seconds: Optional[float]
    created_at: datetime


app = FastAPI(title="Murmur API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
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
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
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


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "transcription": "faster-whisper",
        "model": WHISPER_MODEL,
        "database": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres",
    }


@app.get("/api/murmurs", response_model=list[MurmurRead])
def list_murmurs(space: Optional[str] = None, query: Optional[str] = None) -> list[Murmur]:
    with Session(engine) as session:
        statement = select(Murmur).order_by(Murmur.created_at.desc())
        rows = session.exec(statement).all()
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
    murmur = Murmur(
        title=payload.title or build_title(transcript),
        transcript=transcript,
        space=payload.space or detect_space(transcript),
        source="text",
    )
    with Session(engine) as session:
        session.add(murmur)
        session.commit()
        session.refresh(murmur)
    return murmur


@app.post("/api/transcribe", response_model=MurmurRead)
async def transcribe_audio(
    audio: UploadFile = File(...),
    space: Optional[str] = Form(None),
) -> Murmur:
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
        segments, info = model.transcribe(
            temp_path,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 450},
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech was detected")
        murmur = Murmur(
            title=build_title(transcript),
            transcript=transcript,
            space=space or detect_space(transcript),
            source="voice",
            language=getattr(info, "language", None),
            duration_seconds=getattr(info, "duration", None),
        )
        with Session(engine) as session:
            session.add(murmur)
            session.commit()
            session.refresh(murmur)
        return murmur
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
