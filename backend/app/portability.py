from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

BACKUP_VERSION = 1
MAX_BACKUP_RECORDS = 10_000
MAX_TAGS = 32
DANGEROUS_CSV_PREFIXES = ('=', '+', '-', '@')


class BackupValidationError(ValueError):
    """Raised when a backup cannot be safely restored."""


def safe_csv_cell(value: Any) -> str:
    if value is None:
        return ''
    text = str(value)
    if text.lstrip().startswith(DANGEROUS_CSV_PREFIXES):
        return "'" + text
    return text


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def build_backup(records: Iterable[dict[str, Any]], exported_at: datetime | None = None) -> dict[str, Any]:
    instant = exported_at or datetime.now(timezone.utc)
    return {
        'version': BACKUP_VERSION,
        'exported_at': _iso(instant),
        'records': [deepcopy(record) for record in records],
    }


def _require_timestamp(record: dict[str, Any], field: str, index: int) -> None:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BackupValidationError(f'record {index} {field} must be an ISO timestamp')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise BackupValidationError(f'record {index} {field} must be an ISO timestamp') from exc


def validate_backup(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BackupValidationError('Backup must be a JSON object')
    if payload.get('version') != BACKUP_VERSION:
        raise BackupValidationError(f'Unsupported backup version: {payload.get("version")!r}')

    exported_at = payload.get('exported_at')
    if not isinstance(exported_at, str):
        raise BackupValidationError('exported_at must be an ISO timestamp')
    try:
        datetime.fromisoformat(exported_at.replace('Z', '+00:00'))
    except ValueError as exc:
        raise BackupValidationError('exported_at must be an ISO timestamp') from exc

    records = payload.get('records')
    if not isinstance(records, list):
        raise BackupValidationError('records must be a list')
    if len(records) > MAX_BACKUP_RECORDS:
        raise BackupValidationError(f'Backup may contain at most {MAX_BACKUP_RECORDS} records')

    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    required_text = ('id', 'title', 'transcript', 'space', 'source')

    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise BackupValidationError(f'record {index} must be an object')
        record = deepcopy(raw)
        for field in required_text:
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise BackupValidationError(f'record {index} {field} must be non-empty text')

        record_id = record['id']
        if record_id in seen_ids:
            raise BackupValidationError(f'duplicate record id: {record_id}')
        seen_ids.add(record_id)

        _require_timestamp(record, 'created_at', index)
        if record.get('updated_at') is not None:
            _require_timestamp(record, 'updated_at', index)
        else:
            record['updated_at'] = record['created_at']

        tags = record.get('tags', [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise BackupValidationError(f'record {index} tags must be a list of strings')
        if len(tags) > MAX_TAGS:
            raise BackupValidationError(f'record {index} may contain at most {MAX_TAGS} tags')
        record['tags'] = tags

        pinned = record.get('pinned', False)
        if not isinstance(pinned, bool):
            raise BackupValidationError(f'record {index} pinned must be boolean')
        record['pinned'] = pinned

        normalized.append(record)

    return {
        'version': BACKUP_VERSION,
        'exported_at': exported_at,
        'records': normalized,
    }
