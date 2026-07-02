from __future__ import annotations

import csv
import io
import json as jsonlib
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from . import analysis, integrations
from .skills import find_actions, find_dates, process_with_skill, skill_catalog

try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./murmur.db")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "40"))
DUPLICATE_THRESHOLD = float(os.getenv("DUPLICATE_THRESHOLD", "0.55"))

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
    tags: str = ""  # stored pipe-delimited, exposed as a list
    summary: str = ""
    sentiment: str = "neutral"
    sentiment_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class MurmurCreate(BaseModel):
    transcript: str
    title: Optional[str] = None
    space: Optional[str] = None


class MurmurProcess(BaseModel):
    transcript: str
    skill: Optional[str] = None


class ShareRequest(BaseModel):
    target: str = "slack"  # slack | teams | notion


app = FastAPI(title="Murmur API", version="0.4.0")
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


def serialize(murmur: Murmur) -> dict[str, Any]:
    return {
        "id": murmur.id,
        "title": murmur.title,
        "transcript": murmur.transcript,
        "space": murmur.space,
        "source": murmur.source,
        "language": murmur.language,
        "duration_seconds": murmur.duration_seconds,
        "tags": [tag for tag in murmur.tags.split("|") if tag],
        "summary": murmur.summary,
        "sentiment": murmur.sentiment,
        "sentiment_score": murmur.sentiment_score,
        "created_at": murmur.created_at.isoformat(),
    }


def all_murmurs(session: Session) -> list[Murmur]:
    return session.exec(select(Murmur).order_by(Murmur.created_at.desc())).all()


def save_murmur(transcript: str, source: str, space: Optional[str] = None, language: Optional[str] = None, duration: Optional[float] = None, title: Optional[str] = None) -> Murmur:
    enriched = analysis.enrich(transcript)
    murmur = Murmur(
        title=title or build_title(transcript),
        transcript=transcript,
        space=space or detect_space(transcript),
        source=source,
        language=language,
        duration_seconds=duration,
        tags="|".join(enriched["tags"]),
        summary=enriched["summary"],
        sentiment=enriched["sentiment"]["label"],
        sentiment_score=enriched["sentiment"]["score"],
    )
    with Session(engine) as session:
        session.add(murmur)
        session.commit()
        session.refresh(murmur)
    return murmur


def parse_when(text: str, base: datetime) -> Optional[datetime]:
    """Best-effort resolution of a natural-language date reference to a datetime."""
    lowered = text.lower()
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if "today" in lowered or "tonight" in lowered:
        return base
    if "tomorrow" in lowered:
        return base + timedelta(days=1)
    if "yesterday" in lowered:
        return base - timedelta(days=1)
    for index, day in enumerate(weekdays):
        if day[:3] in lowered:
            delta = (index - base.weekday()) % 7
            return base + timedelta(days=delta or 7)
    months = {m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
    match = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", lowered)
    if match:
        month, day = months[match.group(1)], int(match.group(2))
        try:
            return base.replace(month=month, day=day)
        except ValueError:
            return None
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else base.year
        if year < 100:
            year += 2000
        try:
            return base.replace(year=year, month=month, day=day)
        except ValueError:
            return None
    return None


def migrate() -> None:
    """Add columns introduced after the initial schema (SQLite only, best effort)."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    new_columns = {
        "tags": "TEXT DEFAULT ''",
        "summary": "TEXT DEFAULT ''",
        "sentiment": "TEXT DEFAULT 'neutral'",
        "sentiment_score": "FLOAT DEFAULT 0.0",
    }
    with engine.connect() as connection:
        existing = {row[1] for row in connection.execute(sql_text("PRAGMA table_info(murmur)"))}
        for column, ddl in new_columns.items():
            if column not in existing:
                connection.execute(sql_text(f"ALTER TABLE murmur ADD COLUMN {column} {ddl}"))
        connection.commit()


@app.on_event("startup")
def on_startup() -> None:
    SQLModel.metadata.create_all(engine)
    migrate()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": app.version,
        "transcription": "faster-whisper",
        "model": WHISPER_MODEL,
        "database": "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres",
        "skills": len(skill_catalog()),
        "integrations": integrations.integration_status(),
    }


@app.get("/api/integrations")
def integrations_status() -> dict[str, Any]:
    return integrations.integration_status()


@app.get("/api/skills")
def list_skills() -> list[dict[str, str]]:
    return skill_catalog()


@app.post("/api/process")
def process_murmur(payload: MurmurProcess) -> dict[str, Any]:
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript cannot be empty")
    return process_with_skill(transcript, payload.skill)


@app.get("/api/murmurs")
def list_murmurs(space: Optional[str] = None, query: Optional[str] = None, tag: Optional[str] = None) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = all_murmurs(session)
    if space and space != "All murmurs":
        rows = [row for row in rows if row.space.lower() == space.lower()]
    if tag:
        rows = [row for row in rows if tag.lower() in [t.lower() for t in row.tags.split("|") if t]]
    if query:
        q = query.lower()
        rows = [row for row in rows if q in row.title.lower() or q in row.transcript.lower()]
    return [serialize(row) for row in rows]


@app.post("/api/murmurs")
def create_murmur(payload: MurmurCreate) -> dict[str, Any]:
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript cannot be empty")
    with Session(engine) as session:
        existing = [(row.id, row.transcript) for row in all_murmurs(session)]
    duplicate = analysis.find_duplicate(transcript, existing, threshold=DUPLICATE_THRESHOLD)
    murmur = save_murmur(transcript, "text", payload.space, title=payload.title)
    result = serialize(murmur)
    result["duplicate_of"] = duplicate
    return result


@app.delete("/api/murmurs/{murmur_id}", status_code=204)
def delete_murmur(murmur_id: str) -> Response:
    with Session(engine) as session:
        murmur = session.get(Murmur, murmur_id)
        if not murmur:
            raise HTTPException(status_code=404, detail="Murmur not found")
        session.delete(murmur)
        session.commit()
    return Response(status_code=204)


@app.get("/api/search")
def semantic_search(q: str, limit: int = 20) -> dict[str, Any]:
    """Meaning-based search using TF-IDF cosine similarity over transcripts."""
    query = q.strip()
    if not query:
        return {"query": query, "results": []}
    with Session(engine) as session:
        rows = all_murmurs(session)
    documents = [f"{row.title}. {row.transcript}" for row in rows]
    ranked = analysis.rank_by_similarity(query, documents)
    results = []
    for position, score in ranked:
        if score <= 0:
            continue
        item = serialize(rows[position])
        item["score"] = score
        results.append(item)
        if len(results) >= limit:
            break
    return {"query": query, "results": results}


@app.get("/api/murmurs/{murmur_id}/related")
def related_murmurs(murmur_id: str, limit: int = 4) -> dict[str, Any]:
    with Session(engine) as session:
        target = session.get(Murmur, murmur_id)
        if not target:
            raise HTTPException(status_code=404, detail="Murmur not found")
        others = [(row.id, f"{row.title}. {row.transcript}") for row in all_murmurs(session) if row.id != murmur_id]
        matches = analysis.most_similar(f"{target.title}. {target.transcript}", others, limit=limit)
        by_id = {row.id: row for row in all_murmurs(session)}
    results = []
    for match in matches:
        item = serialize(by_id[match["id"]])
        item["score"] = match["score"]
        results.append(item)
    return {"id": murmur_id, "related": results}


@app.get("/api/tasks")
def action_items() -> dict[str, Any]:
    """Actionable sentences extracted across all murmurs, with resolved due dates."""
    with Session(engine) as session:
        rows = all_murmurs(session)
    tasks = []
    for row in rows:
        base = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        for action in find_actions(row.transcript):
            when = parse_when(action, base)
            tasks.append({
                "murmur_id": row.id,
                "space": row.space,
                "action": action,
                "due": when.date().isoformat() if when else None,
                "created_at": base.isoformat(),
            })
    tasks.sort(key=lambda item: (item["due"] is None, item["due"] or ""))
    return {"count": len(tasks), "tasks": tasks}


@app.get("/api/timeline")
def timeline() -> dict[str, Any]:
    """Murmurs grouped by calendar day, newest first."""
    with Session(engine) as session:
        rows = all_murmurs(session)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        day = (row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)).date().isoformat()
        groups.setdefault(day, []).append(serialize(row))
    days = [{"date": day, "items": items} for day, items in sorted(groups.items(), reverse=True)]
    return {"days": days}


@app.get("/api/tags")
def tag_cloud() -> dict[str, Any]:
    with Session(engine) as session:
        rows = all_murmurs(session)
    counts: dict[str, int] = {}
    for row in rows:
        for tag in row.tags.split("|"):
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {"tags": [{"tag": tag, "count": count} for tag, count in ranked]}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with Session(engine) as session:
        rows = all_murmurs(session)
    by_space: dict[str, int] = {}
    by_sentiment: dict[str, int] = {}
    voice_seconds = 0.0
    for row in rows:
        by_space[row.space] = by_space.get(row.space, 0) + 1
        by_sentiment[row.sentiment] = by_sentiment.get(row.sentiment, 0) + 1
        voice_seconds += row.duration_seconds or 0
    return {
        "total": len(rows),
        "by_space": by_space,
        "by_sentiment": by_sentiment,
        "voice_minutes": round(voice_seconds / 60, 1),
    }


@app.get("/api/export.csv")
def export_csv() -> Response:
    with Session(engine) as session:
        rows = all_murmurs(session)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "title", "transcript", "space", "source", "tags", "sentiment", "language", "duration_seconds", "created_at"])
    for row in rows:
        writer.writerow([row.id, row.title, row.transcript, row.space, row.source, row.tags.replace("|", ","), row.sentiment, row.language or "", row.duration_seconds or "", row.created_at.isoformat()])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=murmurs.csv"})


@app.get("/api/export.json")
def export_json() -> Response:
    with Session(engine) as session:
        rows = all_murmurs(session)
    payload = jsonlib.dumps([serialize(row) for row in rows], indent=2)
    return Response(payload, media_type="application/json", headers={"Content-Disposition": "attachment; filename=murmurs.json"})


@app.get("/api/export.txt")
def export_txt() -> Response:
    """Plain full-text transcript archive."""
    with Session(engine) as session:
        rows = all_murmurs(session)
    blocks = []
    for row in rows:
        blocks.append(f"[{row.created_at.isoformat()}] {row.space} — {row.title}\n{row.transcript}\n")
    return Response("\n".join(blocks), media_type="text/plain", headers={"Content-Disposition": "attachment; filename=murmurs.txt"})


@app.get("/api/calendar.ics")
def calendar_feed() -> Response:
    """Subscribable iCal feed: one event per murmur that carries an action/date."""
    with Session(engine) as session:
        rows = all_murmurs(session)
    events = []
    for row in rows:
        base = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
        actions = find_actions(row.transcript)
        dates = find_dates(row.transcript)
        if not actions and not dates:
            continue
        when = None
        for candidate in dates:
            when = parse_when(candidate, base)
            if when:
                break
        events.append({
            "id": row.id,
            "title": row.title,
            "description": " ".join(actions) or row.transcript,
            "start": when or base,
            "all_day": True,
        })
    ics = integrations.build_ics(events)
    return Response(ics, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=murmur.ics"})


@app.post("/api/murmurs/{murmur_id}/share")
def share_murmur(murmur_id: str, payload: ShareRequest) -> dict[str, Any]:
    with Session(engine) as session:
        murmur = session.get(Murmur, murmur_id)
        if not murmur:
            raise HTTPException(status_code=404, detail="Murmur not found")
    tags = [tag for tag in murmur.tags.split("|") if tag]
    if payload.target == "slack":
        result = integrations.share_to_slack(murmur.title, murmur.transcript, murmur.space)
    elif payload.target == "teams":
        result = integrations.share_to_teams(murmur.title, murmur.transcript, murmur.space)
    elif payload.target == "notion":
        result = integrations.export_to_notion(murmur.title, murmur.transcript, murmur.space, tags)
    else:
        raise HTTPException(status_code=422, detail="Unknown share target")
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result.get("error", "Share failed"))
    return {"target": payload.target, "ok": True}


@app.get("/api/digest")
def digest_preview(days: int = 7) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with Session(engine) as session:
        rows = all_murmurs(session)
    recent = [serialize(row) for row in rows if (row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)) >= cutoff]
    digest = integrations.build_digest(recent, f"the last {days} days")
    digest["can_email"] = integrations.email_configured()
    digest["count"] = len(recent)
    return digest


@app.post("/api/digest/send")
def digest_send(days: int = 7) -> dict[str, Any]:
    preview = digest_preview(days)
    if not integrations.email_configured():
        raise HTTPException(status_code=503, detail="Email is not configured (set SMTP_HOST and DIGEST_TO)")
    result = integrations.send_digest_email(preview)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result.get("error", "Email failed"))
    return {"ok": True, "recipient": result.get("recipient")}


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...), space: Optional[str] = Form(None)) -> dict[str, Any]:
    transcript = await _transcribe_upload(audio)
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was detected")
    murmur = save_murmur(transcript, "voice", space)
    return serialize(murmur)


@app.post("/api/search/voice")
async def voice_search(audio: UploadFile = File(...)) -> dict[str, Any]:
    """Speak a question; we transcribe it and run semantic search."""
    transcript = await _transcribe_upload(audio)
    if not transcript:
        raise HTTPException(status_code=422, detail="No speech was detected")
    return semantic_search(transcript)


async def _transcribe_upload(audio: UploadFile) -> str:
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
        return " ".join(segment.text.strip() for segment in segments).strip()
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
