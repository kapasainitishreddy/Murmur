import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_murmur.db"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def setup_module():
    path = Path("test_murmur.db")
    if path.exists():
        path.unlink()
    with client:
        pass


def teardown_module():
    path = Path("test_murmur.db")
    if path.exists():
        path.unlink()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transcription"] == "faster-whisper"


def test_create_and_list_murmur():
    created = client.post(
        "/api/murmurs",
        json={"transcript": "The checkout button crashes after I apply a coupon."},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["space"] == "Bug report"
    assert payload["source"] == "text"

    listed = client.get("/api/murmurs")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_rejects_empty_transcript():
    response = client.post("/api/murmurs", json={"transcript": "   "})
    assert response.status_code == 422


def test_filter_by_space_and_query():
    client.post("/api/murmurs", json={"transcript": "My passport is under the blue folder."})
    client.post("/api/murmurs", json={"transcript": "The contractor agreed to repair the wall damage."})

    records = client.get("/api/murmurs", params={"space": "Records"})
    assert records.status_code == 200
    assert all(item["space"] == "Records" for item in records.json())

    search = client.get("/api/murmurs", params={"query": "passport"})
    assert search.status_code == 200
    assert any("passport" in item["transcript"].lower() for item in search.json())
