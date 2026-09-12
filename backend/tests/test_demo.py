from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_api import flexible


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "demo.sqlite3")) as client:
        assert client.post("/api/demo/start").status_code == 200
        yield client


def set_time(client, value):
    response = client.put("/api/demo/clock", json={"now": value})
    assert response.status_code == 200
    return response.json()


def add(client, day="2026-09-11", item_id="work", start=0):
    return client.post("/api/items", json={**flexible(item_id, start_slot=start), "date": day, "deadlineSlot": 32})


def move(client, item_id="work", slot=4):
    return client.post("/api/optimizer/preview", json={"operation": {"type": "move", "itemId": item_id, "targetStartSlot": slot}, "timeZone": "UTC"})


def commit(client, preview):
    return client.post("/api/optimizer/commit", json={"previewToken": preview["previewToken"]})


def test_demo_start_is_idempotent_and_persistent(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    with TestClient(create_app(path)) as client:
        before = client.get("/api/demo/clock").json()
        assert before["revision"] == 0
        started = client.post("/api/demo/start").json()
        assert started["now"] == "2026-09-11T08:00:00"
        assert started["timeZone"] == "America/New_York"
        assert started["startDate"] == "2026-09-11" and started["endDate"] == "2026-09-13"
        clock = set_time(client, "2026-09-12T10:15:00")
        assert client.post("/api/demo/start").json() == clock
        assert set_time(client, "2026-09-12T10:15:00") == clock
    with TestClient(create_app(path)) as restarted:
        assert restarted.get("/api/demo/clock").json() == clock
        assert restarted.post("/api/demo/start").json() == clock


@pytest.mark.parametrize("value", ["2026-09-10T23:59:00", "2026-09-14T00:00:00", "2025-09-12T10:00:00", "2026-09-12T10:00:00Z", "invalid"])
def test_clock_rejects_invalid_or_out_of_demo_values(client, value):
    before = client.get("/api/demo/clock").json()
    assert client.put("/api/demo/clock", json={"now": value}).status_code == 422
    assert client.get("/api/demo/clock").json() == before


def test_demo_ignores_real_wall_clock_and_request_timezone(client, frozen_clock):
    frozen_clock[0] = datetime(2030, 1, 1, tzinfo=timezone.utc)
    set_time(client, "2026-09-11T10:15:00")
    response = add(client)
    assert response.status_code == 201
    assert response.json()["items"][0]["startSlot"] == 5
    preview = move(client, slot=6).json()
    assert preview["earliestStartSlot"] == 5
    frozen_clock[0] = datetime(2031, 1, 1, tzinfo=timezone.utc)
    assert commit(client, preview).status_code == 200


def test_three_dates_keep_independent_schedules_and_undo(client):
    original = {}
    for day in ["2026-09-11", "2026-09-12", "2026-09-13"]:
        response = add(client, day, f"work-{day}")
        assert response.status_code == 201
        original[day] = response.json()["items"]
    assert commit(client, move(client, "work-2026-09-11", 4).json()).status_code == 200
    assert commit(client, move(client, "work-2026-09-12", 6).json()).status_code == 200
    assert client.get("/api/day/2026-09-11").json()["canUndo"]
    assert client.get("/api/day/2026-09-12").json()["canUndo"]
    assert client.get("/api/day/2026-09-13").json()["items"] == original["2026-09-13"]
    assert client.post("/api/day/2026-09-11/undo").json()["items"] == original["2026-09-11"]
    assert client.get("/api/day/2026-09-12").json()["items"][0]["startSlot"] == 6
    assert client.post("/api/day/2026-09-12/undo").json()["items"] == original["2026-09-12"]


def test_current_past_and_future_days_follow_demo_clock(client):
    assert add(client).status_code == 201
    set_time(client, "2026-09-12T10:15:00")
    assert add(client, item_id="past").status_code == 409
    assert move(client).status_code == 409
    assert client.get("/api/day/2026-09-11").json()["items"][0]["id"] == "work"
    assert add(client, "2026-09-12", "current").json()["items"][0]["startSlot"] == 5
    assert add(client, "2026-09-13", "future").json()["items"][0]["startSlot"] == 0
    assert add(client, "2026-09-14", "out-of-range").status_code == 409
    set_time(client, "2026-09-11T08:00:00")
    assert move(client).status_code == 200


def test_clock_rewind_invalidates_preview_even_when_cutoff_is_unchanged(client):
    assert add(client).status_code == 201
    proposal = move(client).json()
    before = client.get("/api/day/2026-09-11").json()
    set_time(client, "2026-09-11T07:30:00")  # Same earliest slot, different clock revision.
    assert commit(client, proposal).status_code == 409
    set_time(client, "2026-09-11T08:00:00")  # Returning to the original time doesn't revive it.
    assert commit(client, proposal).status_code == 409
    assert client.get("/api/day/2026-09-11").json() == before


def test_clock_change_preserves_snapshots_and_rejects_old_new_item_options(client):
    assert add(client).status_code == 201
    assert commit(client, move(client).json()).status_code == 200
    before = client.get("/api/day/2026-09-11").json()
    options = client.post("/api/optimizer/proposals", json={"item": {
        "kind": "flexible", "id": "new", "title": "New task", "date": "2026-09-11", "durationSlots": 1, "deadlineSlot": 32,
    }, "timeZone": "America/New_York"}).json()
    set_time(client, "2026-09-12T10:00:00")
    assert client.post(f'/api/optimizer/proposals/{options["proposalSetId"]}/accept', json={"alternativeId": options["alternatives"][0]["id"]}).status_code == 409
    assert client.get("/api/day/2026-09-11").json() == before
    assert client.post("/api/day/2026-09-11/undo").json()["items"][0]["startSlot"] == 0


def test_demo_clock_change_from_another_app_instance_invalidates_tokens(tmp_path):
    path = tmp_path / "shared.sqlite3"
    with TestClient(create_app(path)) as first, TestClient(create_app(path)) as second:
        first.post("/api/demo/start")
        add(first)
        proposal = move(first).json()
        set_time(second, "2026-09-11T07:45:00")
        assert commit(first, proposal).status_code == 409
        assert first.get("/api/demo/clock").json() == second.get("/api/demo/clock").json()


def test_last_day_late_night_defers_instead_of_scheduling_outside_demo(client):
    set_time(client, "2026-09-13T23:45:00")
    response = add(client, "2026-09-13")
    assert response.status_code == 201
    assert response.json()["items"][0]["startSlot"] is None
    assert client.get("/api/day/2026-09-14").json()["items"] == []


def test_samples_on_three_days_use_distinct_ids(client):
    ids = set()
    for day in ["2026-09-11", "2026-09-12", "2026-09-13"]:
        response = client.post(f"/api/day/{day}/seed")
        assert response.status_code == 201
        items = response.json()["items"]
        assert all(item["date"] == day for item in items)
        assert not ids.intersection(item["id"] for item in items)
        ids.update(item["id"] for item in items)


def test_deleting_after_clock_advance_cannot_backfill_elapsed_slots(client):
    assert add(client).status_code == 201
    assert add(client, item_id="future", start=6).status_code == 201
    set_time(client, "2026-09-11T10:15:00")
    result = client.delete("/api/items/work")
    assert result.status_code == 200
    assert result.json()["items"][0]["startSlot"] == 6


def test_add_options_and_running_late_use_simulated_time(client):
    assert add(client, start=4).status_code == 201
    assert add(client, item_id="next", start=6).status_code == 201
    set_time(client, "2026-09-11T10:15:00")
    preview = client.post("/api/optimizer/preview", json={"operation": {"type": "extend", "itemId": "work", "additionalSlots": 2}, "timeZone": "UTC"})
    assert preview.status_code == 200
    assert preview.json()["earliestStartSlot"] == 5
    placed = {item["id"]: item for item in preview.json()["schedule"]["items"]}
    assert placed["work"]["startSlot"] == 4 and placed["work"]["durationSlots"] == 4
    assert placed["next"]["startSlot"] >= 8
    options = client.post("/api/optimizer/proposals", json={"item": {
        "kind": "flexible", "id": "new", "title": "New task", "date": "2026-09-11", "durationSlots": 1, "deadlineSlot": 32,
    }, "timeZone": "UTC"})
    assert options.status_code == 200
    assert all(option["startSlot"] >= 5 for option in options.json()["alternatives"])
