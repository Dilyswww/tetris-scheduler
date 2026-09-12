from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.scheduler import SolverUnavailable
from test_api import DAY, fixed, flexible


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "optimizer.sqlite3")) as client:
        yield client


def preview(client, operation, time_zone="UTC"):
    return client.post("/api/optimizer/preview", json={"operation": operation, "timeZone": time_zone})


def move(item_id="work", slot=2):
    return {"type": "move", "itemId": item_id, "targetStartSlot": slot}


def extend(item_id="work", slots=2):
    return {"type": "extend", "itemId": item_id, "additionalSlots": slots}


def commit(client, proposal):
    return client.post("/api/optimizer/commit", json={"previewToken": proposal["previewToken"]})


def day(client):
    return client.get(f"/api/day/{DAY}").json()


def test_move_can_fill_vacated_earlier_gap_and_commit_exact_preview(client):
    client.post("/api/items", json=flexible(start_slot=0))
    client.post("/api/items", json=flexible("other", start_slot=2))
    before = day(client)
    response = preview(client, move())
    assert response.status_code == 200
    proposal = response.json()
    placed = {item["id"]: item for item in proposal["schedule"]["items"]}
    assert placed["work"]["startSlot"] == 2
    assert placed["other"]["startSlot"] == 0
    assert placed["work"]["durationSlots"] == 2
    assert day(client) == before  # Preview wrote neither items nor Undo.
    saved = commit(client, proposal)
    assert saved.status_code == 200
    assert saved.json()["items"] == proposal["schedule"]["items"]
    assert saved.json()["changes"] == proposal["schedule"]["changes"]
    assert saved.json()["canUndo"]
    assert commit(client, proposal).status_code == 409
    undone = client.post(f"/api/day/{DAY}/undo")
    assert undone.json()["items"] == before["items"]


def test_extension_keeps_start_and_moves_other_work_later(client):
    client.post("/api/items", json=flexible(start_slot=0))
    client.post("/api/items", json=flexible("other", start_slot=2))
    proposal = preview(client, extend()).json()
    placed = {item["id"]: item for item in proposal["schedule"]["items"]}
    assert placed["work"]["startSlot"] == 0
    assert placed["work"]["durationSlots"] == 4
    assert placed["other"]["startSlot"] == 4
    assert [c["changeType"] for c in proposal["schedule"]["changes"]] == ["extended", "moved"]


def test_drag_30_90_60_minutes_reorders_within_original_three_hours(client):
    for item_id, start, duration in [("short", 0, 1), ("long", 1, 3), ("medium", 4, 2)]:
        assert client.post("/api/items", json={**flexible(item_id, start_slot=start), "durationSlots": duration, "deadlineSlot": 32}).status_code == 201
    before = day(client)
    response = preview(client, move("short", 5))
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["penalties"] == {"movedTask": 1, "displacementSlot": 2, "largestDisplacementSlot": 4}
    assert {item["id"]: item["startSlot"] for item in proposal["schedule"]["items"]} == {"short": 5, "long": 0, "medium": 3}
    assert proposal["schedule"]["solverStatus"] == "optimal"
    assert day(client) == before
    assert commit(client, proposal).json()["items"] == proposal["schedule"]["items"]
    assert client.post(f"/api/day/{DAY}/undo").json()["items"] == before["items"]

    # Users can deliberately choose stability over smaller individual moves.
    override = client.post("/api/optimizer/preview", json={"operation": move("short", 5), "timeZone": "UTC", "penalties": {"movedTask": 100}})
    assert override.status_code == 200
    assert {item["id"]: item["startSlot"] for item in override.json()["schedule"]["items"]} == {"short": 5, "long": 1, "medium": 6}


def test_extension_uses_its_own_defaults_and_merges_partial_overrides(client):
    client.post("/api/items", json=flexible(start_slot=0))
    assert preview(client, extend()).json()["penalties"] == {"movedTask": 8, "displacementSlot": 2, "largestDisplacementSlot": 0}
    response = client.post("/api/optimizer/preview", json={"operation": extend(), "timeZone": "UTC", "penalties": {"displacementSlot": 5}})
    assert response.json()["penalties"] == {"movedTask": 8, "displacementSlot": 5, "largestDisplacementSlot": 0}


@pytest.mark.parametrize("weights", [{"movedTask": -1}, {"displacementSlot": 1001}, {"largestDisplacementSlot": 0.5}, {"movedTask": True}, {"unknown": 3}])
def test_penalty_overrides_are_validated(client, weights):
    response = client.post("/api/optimizer/preview", json={"operation": move(), "timeZone": "UTC", "penalties": weights})
    assert response.status_code == 422


@pytest.mark.parametrize("protected", [fixed(start_slot=2), {**flexible("pinned", start_slot=2), "isPinned": True}])
def test_protected_drop_conflict_is_atomic(client, protected):
    client.post("/api/items", json=flexible(start_slot=0))
    client.post("/api/items", json=protected)
    before = day(client)
    assert preview(client, move()).status_code == 409
    assert day(client) == before
    assert preview(client, move(protected["id"], 6)).status_code == 409


def test_preview_preserves_existing_undo_and_stale_commit_cannot_overwrite_edit(client):
    client.post("/api/items", json=flexible(start_slot=0))
    assert commit(client, preview(client, move()).json()).status_code == 200
    before = day(client)
    proposal = preview(client, move(slot=4)).json()
    assert day(client) == before
    item = {**before["items"][0], "title": "Edited elsewhere"}
    assert client.put("/api/items/work", json=item).status_code == 200
    edited = day(client)
    assert commit(client, proposal).status_code == 409
    assert day(client) == edited


def test_revision_rejects_preview_even_after_undo_restores_identical_items(client):
    client.post("/api/items", json=flexible(start_slot=0))
    first = preview(client, move(slot=2)).json()
    before = day(client)
    assert commit(client, preview(client, move(slot=4)).json()).status_code == 200
    assert client.post(f"/api/day/{DAY}/undo").status_code == 200
    assert day(client)["items"] == before["items"]
    assert commit(client, first).status_code == 409


def test_elapsed_gaps_unavailable_but_selected_past_task_can_move_forward(client, frozen_clock):
    client.post("/api/items", json=flexible("completed", start_slot=0))
    client.post("/api/items", json={**flexible("current", start_slot=4), "deadlineSlot": 12})
    client.post("/api/items", json={**flexible("next", start_slot=6), "deadlineSlot": 8})
    frozen_clock[0] = datetime(2026, 9, 12, 10, 15, tzinfo=timezone.utc)
    proposal = preview(client, extend("current")).json()
    assert proposal["earliestStartSlot"] == 5  # Round 10:15 up to 10:30.
    placed = {item["id"]: item for item in proposal["schedule"]["items"]}
    assert placed["completed"]["startSlot"] == 0
    assert placed["current"]["startSlot"] == 4
    assert placed["next"]["startSlot"] is None  # The old 9–10 AM gap is elapsed.
    moved = preview(client, move("completed", 8))
    assert moved.status_code == 200
    moved_items = {item["id"]: item for item in moved.json()["schedule"]["items"]}
    assert moved_items["completed"]["startSlot"] == 8
    assert moved_items["current"]["startSlot"] == 4  # Other elapsed work remains locked.
    assert preview(client, move("next", 3)).status_code == 409


def test_future_work_can_move_earlier_but_never_before_current_cutoff(client, frozen_clock):
    client.post("/api/items", json=flexible(start_slot=8))
    client.post("/api/items", json=flexible("other", start_slot=6))
    frozen_clock[0] = datetime(2026, 9, 12, 10, 15, tzinfo=timezone.utc)
    proposal = preview(client, move(slot=6)).json()
    placed = {item["id"]: item for item in proposal["schedule"]["items"]}
    assert placed["work"]["startSlot"] == 6
    assert placed["other"]["startSlot"] == 8
    assert all(item["startSlot"] >= 5 for item in placed.values())


def test_time_boundary_change_rejects_commit_without_writes(client, frozen_clock):
    client.post("/api/items", json=flexible(start_slot=4))
    proposal = preview(client, move(slot=2)).json()
    before = day(client)
    frozen_clock[0] = datetime(2026, 9, 12, 8, 1, tzinfo=timezone.utc)
    assert commit(client, proposal).status_code == 409
    assert day(client) == before


def test_timezone_and_past_day_validation(client, frozen_clock):
    client.post("/api/items", json=flexible(start_slot=8))
    frozen_clock[0] = datetime(2026, 9, 12, 14, 15, tzinfo=timezone.utc)
    assert preview(client, move(slot=6), "America/New_York").json()["earliestStartSlot"] == 5
    assert preview(client, move(), "Invalid/Zone").status_code == 409
    frozen_clock[0] = datetime(2026, 9, 13, 8, tzinfo=timezone.utc)
    assert preview(client, move()).status_code == 409


def test_expiration_and_server_restart_require_new_preview(tmp_path, monkeypatch):
    database = tmp_path / "restart.sqlite3"
    moment = [0]
    monkeypatch.setattr("app.repository.time.monotonic", lambda: moment[0])
    with TestClient(create_app(database)) as client:
        client.post("/api/items", json=flexible(start_slot=0))
        proposal = preview(client, move()).json()
        moment[0] = 121
        assert commit(client, proposal).status_code == 409
        proposal = preview(client, move()).json()
    with TestClient(create_app(database)) as client:
        assert commit(client, proposal).status_code == 409
        assert day(client)["items"][0]["startSlot"] == 0


@pytest.mark.parametrize("operation", [move(slot=32), move(slot=-1), extend(slots=0), extend(slots=5),
    {**move(), "additionalSlots": 1}, {"type": "unknown", "itemId": "work"}])
def test_request_union_validation(client, operation):
    assert preview(client, operation).status_code == 422


def test_solver_timeout_preserves_day_and_existing_undo(client, monkeypatch):
    client.post("/api/items", json=flexible(start_slot=0))
    assert commit(client, preview(client, move()).json()).status_code == 200
    before = day(client)
    def unavailable(*args, **kwargs):
        raise SolverUnavailable("No solution found within the time limit.")
    monkeypatch.setattr("app.repository.schedule_items", unavailable)
    assert preview(client, move(slot=4)).status_code == 503
    assert day(client) == before


def test_drag_can_place_previously_deferred_task(client):
    client.post("/api/items", json={**flexible("other", start_slot=0), "deadlineSlot": 2})
    client.post("/api/items", json={**flexible(), "deadlineSlot": 2})
    assert day(client)["items"][1]["startSlot"] is None
    proposal = preview(client, move(slot=0)).json()
    placed = {item["id"]: item for item in proposal["schedule"]["items"]}
    assert placed["work"]["startSlot"] == 0
    assert placed["other"]["startSlot"] is None
