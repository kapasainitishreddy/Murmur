from datetime import datetime, timezone

import pytest

from app.portability import BackupValidationError, build_backup, safe_csv_cell, validate_backup


def record(record_id='1', **overrides):
    base = {
        'id': record_id,
        'title': 'Passport location',
        'transcript': 'Passport is in the black suitcase.',
        'space': 'Memory',
        'source': 'text',
        'language': None,
        'duration_seconds': None,
        'created_at': '2026-09-07T04:00:00+00:00',
        'updated_at': '2026-09-07T04:00:00+00:00',
        'tags': ['travel', 'important'],
        'pinned': True,
    }
    base.update(overrides)
    return base


def test_safe_csv_cell_neutralizes_formula_prefixes_after_whitespace():
    for value in ['=2+2', '+cmd', '-10+20', '@SUM(A1:A2)', '  =HYPERLINK("x")']:
        safe = safe_csv_cell(value)
        assert safe.startswith("'")
        assert safe.endswith(value)

    assert safe_csv_cell('normal text') == 'normal text'
    assert safe_csv_cell(None) == ''


def test_validate_backup_accepts_roundtrip_envelope():
    exported_at = datetime(2026, 9, 7, 4, tzinfo=timezone.utc)
    envelope = build_backup([record()], exported_at=exported_at)

    parsed = validate_backup(envelope)

    assert parsed['version'] == 1
    assert parsed['exported_at'] == exported_at.isoformat()
    assert parsed['records'][0]['id'] == '1'
    assert parsed['records'][0]['pinned'] is True
    assert parsed['records'][0]['tags'] == ['travel', 'important']


def test_validate_backup_rejects_duplicate_ids_before_restore():
    envelope = build_backup([record('same'), record('same')])

    with pytest.raises(BackupValidationError, match='duplicate record id'):
        validate_backup(envelope)


def test_validate_backup_rejects_unknown_version_and_bad_timestamp():
    envelope = build_backup([record()])
    envelope['version'] = 2
    with pytest.raises(BackupValidationError, match='Unsupported backup version'):
        validate_backup(envelope)

    envelope = build_backup([record(created_at='not-a-date')])
    with pytest.raises(BackupValidationError, match='created_at'):
        validate_backup(envelope)


def test_validate_backup_rejects_unbounded_records_and_tags():
    envelope = build_backup([record(tags=['x'] * 33)])
    with pytest.raises(BackupValidationError, match='at most 32 tags'):
        validate_backup(envelope)

    envelope = build_backup([record(str(i)) for i in range(10001)])
    with pytest.raises(BackupValidationError, match='at most 10000 records'):
        validate_backup(envelope)
