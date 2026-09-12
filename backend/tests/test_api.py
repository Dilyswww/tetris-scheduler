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


def test_update_keeps_identity_and_reschedules_atomically(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        client.post("/api/items", json=flexible())
        client.post("/api/items", json=fixed())

        updated_item = {**flexible(), "title": "Renamed work", "durationSlots": 3, "deadlineSlot": 12, "startSlot": 2}
        response = client.put("/api/items/work", json=updated_item)
        assert response.status_code == 200
        updated = next(item for item in response.json()["items"] if item["id"] == "work")
        assert updated["title"] == "Renamed work"
        assert updated["durationSlots"] == 3
        assert updated["startSlot"] == 2

        conflict = client.put("/api/items/work", json={**fixed("work"), "title": "Conflicting work", "durationSlots": 3})
        assert conflict.status_code == 409
        saved = next(item for item in client.get(f"/api/day/{DAY}").json()["items"] if item["id"] == "work")
        assert saved == updated


def test_update_rejects_identity_or_date_changes(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        client.post("/api/items", json=flexible())
        assert client.put("/api/items/work", json=flexible("different")).status_code == 409
        tomorrow = date(2026, 9, 13)
        assert client.put("/api/items/work", json={**flexible(), "date": tomorrow.isoformat()}).status_code == 409


def test_edit_after_running_late_invalidates_undo_only_on_success(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        assert client.post("/api/items", json=fixed()).status_code == 201
        assert client.post("/api/items", json=flexible(start_slot=2)).status_code == 201
        adjusted = client.post("/api/reschedule", json={"itemId": "meeting", "additionalSlots": 1})
        assert adjusted.status_code == 200
        assert adjusted.json()["canUndo"] is True

        conflict = client.put("/api/items/work", json=fixed("work"))
        assert conflict.status_code == 409
        saved = client.get(f"/api/day/{DAY}").json()
        assert saved["canUndo"] is True
        assert saved["items"] == adjusted.json()["items"]

        work = next(item for item in saved["items"] if item["id"] == "work")
        edited = client.put("/api/items/work", json={**work, "title": "Edited after delay"})
        assert edited.status_code == 200
        assert edited.json()["solverStatus"] in ("optimal", "feasible")
        assert edited.json()["canUndo"] is False
        assert client.post(f"/api/day/{DAY}/undo").status_code == 409
        assert next(item for item in client.get(f"/api/day/{DAY}").json()["items"] if item["id"] == "work")["title"] == "Edited after delay"


def test_running_late_moves_only_the_conflict_and_undo_restores_exact_state(tmp_path):
    database = tmp_path / "test.sqlite3"
    app = create_app(database)
    with TestClient(app) as client:
        client.post("/api/items", json=fixed())
        client.post("/api/items", json=flexible(start_slot=2))
        pinned = {**flexible("gym", start_slot=4), "title": "Gym", "isPinned": True, "deadlineSlot": 20}
        client.post("/api/items", json=pinned)
        before = client.get(f"/api/day/{DAY}").json()["items"]

        response = client.post("/api/reschedule", json={"itemId": "meeting", "additionalSlots": 2})
        assert response.status_code == 200
        body = response.json()
        placed = {item["id"]: item for item in body["items"]}
        assert placed["meeting"]["durationSlots"] == 4
        assert placed["work"]["startSlot"] == 6
        assert placed["gym"]["startSlot"] == 4
        assert body["canUndo"] is True
        assert body["solverStatus"] == "optimal"
        assert [change["changeType"] for change in body["changes"]] == ["extended", "moved"]
        assert all(change["reason"] for change in body["changes"])
        assert client.get(f"/api/day/{DAY}").json()["canUndo"] is True

        undone = client.post(f"/api/day/{DAY}/undo")
        assert undone.status_code == 200
        assert undone.json()["items"] == before
        assert undone.json()["canUndo"] is False
        assert {change["changeType"] for change in undone.json()["changes"]} == {"restored"}
        assert client.post(f"/api/day/{DAY}/undo").status_code == 409

    with TestClient(create_app(database)) as restarted_client:
        assert restarted_client.get(f"/api/day/{DAY}").json()["items"] == before


def test_running_late_defers_work_when_no_valid_gap_remains(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        client.post("/api/items", json=fixed())
        client.post("/api/items", json={**flexible(start_slot=2), "deadlineSlot": 6})
        client.post("/api/items", json={**flexible("gym", start_slot=4), "isPinned": True, "deadlineSlot": 6})

        response = client.post("/api/reschedule", json={"itemId": "meeting", "additionalSlots": 2})
        assert response.status_code == 200
        work = next(item for item in response.json()["items"] if item["id"] == "work")
        assert work["startSlot"] is None
        assert any(change["changeType"] == "deferred" for change in response.json()["changes"])


def test_running_late_validation_and_missing_items_leave_day_unchanged(tmp_path):
    app = create_app(tmp_path / "test.sqlite3")
    with TestClient(app) as client:
        client.post("/api/items", json=fixed())
        before = client.get(f"/api/day/{DAY}").json()["items"]
        assert client.post("/api/reschedule", json={"itemId": "meeting", "additionalSlots": 0}).status_code == 422
        assert client.post("/api/reschedule", json={"itemId": "missing", "additionalSlots": 1}).status_code == 404
        too_long = client.post("/api/reschedule", json={"itemId": "meeting", "additionalSlots": 4})
        assert too_long.status_code == 200
        # A second maximum extension would cross neither the API's request limit nor midnight here;
        # use an event at the end of the day to cover that boundary.
        client.delete("/api/items/meeting")
        client.post("/api/items", json=fixed("late", start_slot=30))
        assert client.post("/api/reschedule", json={"itemId": "late", "additionalSlots": 1}).status_code == 409
        assert next(item for item in client.get(f"/api/day/{DAY}").json()["items"] if item["id"] == "late")["durationSlots"] == 2
