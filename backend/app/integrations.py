"""External integrations for Murmur.

Slack/Teams sharing, Notion export, iCal feeds, and email digests. Every
integration reads its configuration from environment variables and degrades
gracefully: when a service is not configured the API reports it as unavailable
instead of failing. Only the Python standard library is used.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Iterable, Optional

USER_AGENT = "Murmur/0.4 (+https://murmur.app)"


def _post_json(url: str, payload: dict[str, Any], headers: Optional[dict[str, str]] = None, timeout: int = 10) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8") or "{}"
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
            return {"ok": True, "status": response.status, "response": parsed}
    except urllib.error.HTTPError as error:
        return {"ok": False, "status": error.code, "error": error.read().decode("utf-8", "ignore")}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {"ok": False, "status": 0, "error": str(error)}


# --- Slack / Microsoft Teams --------------------------------------------------

def slack_configured() -> bool:
    return bool(os.getenv("SLACK_WEBHOOK_URL"))


def teams_configured() -> bool:
    return bool(os.getenv("TEAMS_WEBHOOK_URL"))


def share_to_slack(title: str, transcript: str, space: str) -> dict[str, Any]:
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return {"ok": False, "status": 0, "error": "SLACK_WEBHOOK_URL is not configured"}
    text = f":speech_balloon: *{title}*\n{transcript}\n_Space: {space}_"
    return _post_json(url, {"text": text})


def share_to_teams(title: str, transcript: str, space: str) -> dict[str, Any]:
    url = os.getenv("TEAMS_WEBHOOK_URL")
    if not url:
        return {"ok": False, "status": 0, "error": "TEAMS_WEBHOOK_URL is not configured"}
    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": title,
        "themeColor": "C9FF68",
        "title": title,
        "text": f"{transcript}\n\n**Space:** {space}",
    }
    return _post_json(url, card)


# --- Notion -------------------------------------------------------------------

def notion_configured() -> bool:
    return bool(os.getenv("NOTION_TOKEN") and os.getenv("NOTION_DATABASE_ID"))


def export_to_notion(title: str, transcript: str, space: str, tags: Optional[list[str]] = None) -> dict[str, Any]:
    token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DATABASE_ID")
    if not token or not database_id:
        return {"ok": False, "status": 0, "error": "NOTION_TOKEN and NOTION_DATABASE_ID are required"}
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": title[:200]}}]},
            "Space": {"select": {"name": space}},
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": transcript[:1900]}}]},
            }
        ],
    }
    if tags:
        payload["properties"]["Tags"] = {"multi_select": [{"name": tag} for tag in tags[:10]]}
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }
    return _post_json("https://api.notion.com/v1/pages", payload, headers=headers)


# --- iCal / calendar ----------------------------------------------------------

def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    if len(line) <= 73:
        return line
    chunks = [line[:73]]
    rest = line[73:]
    while rest:
        chunks.append(" " + rest[:72])
        rest = rest[72:]
    return "\r\n".join(chunks)


def build_ics(events: Iterable[dict[str, Any]], calendar_name: str = "Murmur") -> str:
    """events: dicts with id, title, description, start (datetime), optional all_day."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Murmur//Voice Workspace//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(calendar_name)}",
    ]
    for event in events:
        start: datetime = event["start"]
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        all_day = event.get("all_day", True)
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{event['id']}@murmur.app")
        lines.append(f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
        if all_day:
            lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(start + timedelta(days=1)).strftime('%Y%m%d')}")
        else:
            lines.append(f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"DTEND:{(start + timedelta(hours=1)).strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(_fold(f"SUMMARY:{_ics_escape(event['title'])}"))
        if event.get("description"):
            lines.append(_fold(f"DESCRIPTION:{_ics_escape(event['description'])}"))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


# --- Email digest -------------------------------------------------------------

def email_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("DIGEST_TO"))


def build_digest(murmurs: list[dict[str, Any]], period_label: str = "this week") -> dict[str, str]:
    """Compose a plaintext + HTML weekly digest from recent murmurs."""
    by_space: dict[str, list[dict[str, Any]]] = {}
    for murmur in murmurs:
        by_space.setdefault(murmur["space"], []).append(murmur)
    header = f"Your Murmur digest for {period_label}: {len(murmurs)} captures across {len(by_space)} spaces."
    text_lines = [header, ""]
    html_lines = [f"<h2>Murmur digest</h2><p>{header}</p>"]
    for space, entries in sorted(by_space.items()):
        text_lines.append(f"# {space} ({len(entries)})")
        html_lines.append(f"<h3>{space} <small>({len(entries)})</small></h3><ul>")
        for entry in entries[:8]:
            summary = entry.get("summary") or entry.get("transcript", "")
            text_lines.append(f"  - {entry['title']}: {summary}")
            html_lines.append(f"<li><strong>{entry['title']}</strong> — {summary}</li>")
        html_lines.append("</ul>")
        text_lines.append("")
    return {
        "subject": f"Murmur digest — {len(murmurs)} captures {period_label}",
        "text": "\n".join(text_lines).strip(),
        "html": "".join(html_lines),
    }


def send_digest_email(digest: dict[str, str]) -> dict[str, Any]:
    host = os.getenv("SMTP_HOST")
    recipient = os.getenv("DIGEST_TO")
    if not host or not recipient:
        return {"ok": False, "status": 0, "error": "SMTP_HOST and DIGEST_TO are required"}
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("DIGEST_FROM", username or "murmur@localhost")

    message = EmailMessage()
    message["Subject"] = digest["subject"]
    message["From"] = sender
    message["To"] = recipient
    message.set_content(digest["text"])
    message.add_alternative(f"<html><body>{digest['html']}</body></html>", subtype="html")

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                if username:
                    server.login(username, password or "")
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=context)
                if username:
                    server.login(username, password or "")
                server.send_message(message)
        return {"ok": True, "status": 200, "recipient": recipient}
    except (smtplib.SMTPException, OSError) as error:
        return {"ok": False, "status": 0, "error": str(error)}


def integration_status() -> dict[str, bool]:
    return {
        "slack": slack_configured(),
        "teams": teams_configured(),
        "notion": notion_configured(),
        "email": email_configured(),
    }
