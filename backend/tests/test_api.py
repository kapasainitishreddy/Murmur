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


def test_health_and_skill_catalog():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["transcription"] == "faster-whisper"

    skills = client.get("/api/skills")
    assert skills.status_code == 200
    ids = {skill["id"] for skill in skills.json()}
    assert {"memory", "decision", "bug", "inspection", "care", "inventory", "sop", "complaint", "dream"}.issubset(ids)


def test_create_list_filter_and_search():
    bug = client.post("/api/murmurs", json={"transcript": "The checkout button crashes after I apply a coupon."})
    assert bug.status_code == 200
    assert bug.json()["space"] == "Bug report"

    client.post("/api/murmurs", json={"transcript": "My passport is under the blue folder."})
    client.post("/api/murmurs", json={"transcript": "The contractor agreed to repair the wall damage."})

    records = client.get("/api/murmurs", params={"space": "Records"})
    assert records.status_code == 200
    assert records.json()
    assert all(item["space"] == "Records" for item in records.json())

    search = client.get("/api/murmurs", params={"query": "passport"})
    assert search.status_code == 200
    assert any("passport" in item["transcript"].lower() for item in search.json())


def test_structured_skill_processing():
    bug = client.post("/api/process", json={"transcript": "After I tap Pay, the app crashes instead of showing confirmation."})
    assert bug.status_code == 200
    assert bug.json()["skill"]["id"] == "bug"
    assert bug.json()["result"]["reproduction_steps"]

    decision = client.post("/api/process", json={"transcript": "I decided to use Postgres because I need reliable sync.", "skill": "decision"})
    assert decision.status_code == 200
    assert decision.json()["result"]["reason"] == "I need reliable sync"

    inventory = client.post("/api/process", json={"transcript": "Inventory has 6 blue shirts, 3 damaged boxes.", "skill": "inventory"})
    assert inventory.status_code == 200
    assert len(inventory.json()["result"]["items"]) == 2


def test_stats_export_delete_and_validation():
    empty = client.post("/api/murmurs", json={"transcript": "   "})
    assert empty.status_code == 422

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] >= 3

    export = client.get("/api/export.csv")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "transcript" in export.text.splitlines()[0]

    created = client.post("/api/murmurs", json={"transcript": "Temporary note to delete."}).json()
    deleted = client.delete(f"/api/murmurs/{created['id']}")
    assert deleted.status_code == 204
    missing = client.delete(f"/api/murmurs/{created['id']}")
    assert missing.status_code == 404
