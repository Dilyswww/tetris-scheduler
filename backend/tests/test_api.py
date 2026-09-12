from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app

DAY = date(2026, 9, 12)


def flexible(item_id="work", *, start_slot=None):
    return {
        "id": item_id,
        "title": "Focused work",
        "date": DAY.isoformat(),
        "kind": "flexible",
        "startSlot": start_slot,
        "durationSlots": 2,
        "deadlineSlot": 10,
        "isPinned": False,
        "accent": "purple",
        "note": "",
    }


def fixed(item_id="meeting", *, start_slot=0):
    return {
        "id": item_id,
        "title": "Meeting",
        "date": DAY.isoformat(),
        "kind": "fixed",
        "startSlot": start_slot,
        "durationSlots": 2,
        "isPinned": False,
        "accent": "blue",
        "note": "",
    }


def test_crud_persists_and_reschedules(tmp_path):
    database = tmp_path / "test.sqlite3"
    app = create_app(database)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get(f"/api/day/{DAY}").json()["items"] == []

        created = client.post("/api/items", json=flexible()).json()
        assert created["items"][0]["startSlot"] == 0

        # A new fixed event owns that time and causes the flexible task to move.
        response = client.post("/api/items", json=fixed())
        assert response.status_code == 201
        placed = {item["id"]: item for item in response.json()["items"]}
        assert placed["meeting"]["startSlot"] == 0
        assert placed["work"]["startSlot"] == 2

        pinned = client.patch("/api/items/work", json={"isPinned": True})
        assert pinned.status_code == 200
        assert next(item for item in pinned.json()["items"] if item["id"] == "work")["isPinned"] is True

        deleted = client.delete("/api/items/meeting")
        assert [item["id"] for item in deleted.json()["items"]] == ["work"]
        assert [item["id"] for item in client.get(f"/api/day/{DAY}").json()["items"]] == ["work"]

    # A fresh application instance sees the same saved SQLite state.
    with TestClient(create_app(database)) as restarted_client:
        assert [item["id"] for item in restarted_client.get(f"/api/day/{DAY}").json()["items"]] == ["work"]


def test_conflicts_and_validation_are_atomic(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        client.post("/api/items", json=fixed())
        response = client.post("/api/items", json=fixed("overlap", start_slot=1))
        assert response.status_code == 409
        assert len(client.get(f"/api/day/{DAY}").json()["items"]) == 1
        assert client.post("/api/items", json={**flexible("invalid"), "durationSlots": 0}).status_code == 422
        assert client.delete("/api/items/missing").status_code == 404


def test_seed_only_populates_an_empty_day(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        seeded = client.post(f"/api/day/{DAY}/seed")
        assert seeded.status_code == 201
        assert len(seeded.json()["items"]) == 8
        assert client.post(f"/api/day/{DAY}/seed").status_code == 409
