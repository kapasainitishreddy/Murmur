from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

TESTS = [
    BACKEND / "tests" / "test_portability.py",
    BACKEND / "tests" / "test_upload_policy.py",
    BACKEND / "tests" / "test_transcribe_source_contract.py",
    BACKEND / "tests" / "test_data_ownership_source_contract.py",
    BACKEND / "tests" / "test_schema_migration.py",
    BACKEND / "tests" / "test_metadata_source_contract.py",
]

raise SystemExit(pytest.main(["-q", *map(str, TESTS)]))
