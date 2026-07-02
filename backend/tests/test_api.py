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


def test_create_enriches_tags_sentiment_and_duplicates():
    first = client.post("/api/murmurs", json={"transcript": "The payment button crashes and the checkout is broken."})
    assert first.status_code == 200
    body = first.json()
    assert isinstance(body["tags"], list) and body["tags"]
    assert body["sentiment"] == "negative"
    assert body["summary"]
    assert body["duplicate_of"] is None

    dupe = client.post("/api/murmurs", json={"transcript": "The payment button crashes and checkout is broken."})
    assert dupe.status_code == 200
    assert dupe.json()["duplicate_of"] is not None


def test_semantic_search_and_related_and_tags():
    client.post("/api/murmurs", json={"transcript": "I hid the spare house key under the garden gnome."})
    search = client.get("/api/search", params={"q": "where did I put the key"})
    assert search.status_code == 200
    assert search.json()["results"]
    assert any("key" in item["transcript"].lower() for item in search.json()["results"])

    created = client.post("/api/murmurs", json={"transcript": "Remember the spare key is near the gnome by the door."}).json()
    related = client.get(f"/api/murmurs/{created['id']}/related")
    assert related.status_code == 200
    assert "related" in related.json()

    tags = client.get("/api/tags")
    assert tags.status_code == 200
    assert "tags" in tags.json()


def test_tasks_timeline_and_exports():
    client.post("/api/murmurs", json={"transcript": "Call the plumber tomorrow and email the landlord on Friday."})
    tasks = client.get("/api/tasks")
    assert tasks.status_code == 200
    assert tasks.json()["count"] >= 1
    assert any(task["due"] for task in tasks.json()["tasks"])

    timeline = client.get("/api/timeline")
    assert timeline.status_code == 200
    assert timeline.json()["days"]

    for path, media in [("/api/export.json", "application/json"), ("/api/export.txt", "text/plain"), ("/api/calendar.ics", "text/calendar")]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(media)
    assert "BEGIN:VCALENDAR" in client.get("/api/calendar.ics").text


def test_integrations_and_digest():
    status = client.get("/api/integrations")
    assert status.status_code == 200
    assert set(status.json().keys()) == {"slack", "teams", "notion", "email"}

    digest = client.get("/api/digest")
    assert digest.status_code == 200
    assert "subject" in digest.json()
    assert digest.json()["can_email"] is False

    # Sending should fail cleanly when email is not configured.
    send = client.post("/api/digest/send")
    assert send.status_code == 503


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
