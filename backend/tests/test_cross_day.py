import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import Repository

DAYS = ["2026-09-11", "2026-09-12", "2026-09-13"]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "cross-day.sqlite3")) as client:
        client.post("/api/demo/start")
        yield client


def task(item_id="work", day=DAYS[0], start=None, duration=2, deadline_day=DAYS[1], deadline=32, pinned=False):
    return dict(id=item_id, title=item_id, date=day, kind="flexible", startSlot=start,
        durationSlots=duration, deadlineDate=deadline_day, earliestDate=day,
        deadlineSlot=deadline, isPinned=pinned)


def fixed(item_id, day, start, duration):
    return dict(id=item_id, title=item_id, date=day, kind="fixed", startSlot=start, durationSlots=duration)


def add(client, item):
    response = client.post("/api/items", json=item)
    assert response.status_code == 201, response.text
    return response.json()


def all_items(schedule):
    return {item["id"]: item for plan in schedule["days"] for item in plan["items"]}


def saved(client):
    return {day: client.get(f"/api/day/{day}").json()["items"] for day in DAYS}


def preview(client, operation, penalties=None):
    return client.post("/api/optimizer/preview", json={"operation": operation, "timeZone": "America/New_York", "penalties": penalties})


def late_setup(client):
    add(client, fixed("busy", DAYS[0], 0, 28))
    add(client, fixed("late", DAYS[0], 28, 2))
    add(client, task(start=30, deadline=4))


def test_extension_moves_task_to_tomorrow_and_undo_restores_all_days(client):
    late_setup(client)
    add(client, fixed("tomorrow-meeting", DAYS[1], 0, 2))
    before = saved(client)
    response = preview(client, {"type": "extend", "itemId": "late", "additionalSlots": 2})
    assert response.status_code == 200, response.text
    plan = response.json()
    result = all_items(plan["schedule"])
    assert (result["work"]["date"], result["work"]["startSlot"]) == (DAYS[1], 2)
    assert result["work"]["durationSlots"] == 2
    assert result["late"]["date"] == DAYS[0] and result["late"]["durationSlots"] == 4
    change = next(change for change in plan["schedule"]["changes"] if change["itemId"] == "work")
    assert (change["fromDate"], change["toDate"]) == (DAYS[0], DAYS[1])
    assert saved(client) == before
    committed = client.post("/api/optimizer/commit", json={"previewToken": plan["previewToken"]})
    assert committed.status_code == 200
    assert committed.json()["days"] == plan["schedule"]["days"]
    assert len(all_items(committed.json())) == 4
    # Undo is available from the destination tab and restores both source and destination.
    assert client.post(f"/api/day/{DAYS[1]}/undo").status_code == 200
    assert saved(client) == before
    assert all(not client.get(f"/api/day/{day}").json()["canUndo"] for day in DAYS)


def test_same_day_legacy_deadline_does_not_silently_expand(client):
    add(client, fixed("full", DAYS[0], 0, 32))
    legacy = task()
    del legacy["deadlineDate"]
    del legacy["earliestDate"]
    result = all_items(add(client, legacy))["work"]
    assert result["startSlot"] is None
    assert result["deadlineDate"] == DAYS[0]


def test_task_cannot_combine_evening_and_next_morning_fragments(client):
    add(client, fixed("day-one", DAYS[0], 0, 30))
    add(client, fixed("day-two", DAYS[1], 2, 30))
    result = all_items(add(client, task(duration=4)))["work"]
    assert result["startSlot"] is None  # Two slots each day cannot form one four-slot task.
    assert result["durationSlots"] == 4


def test_deadline_time_only_applies_on_deadline_day(client):
    result = all_items(add(client, task(start=28, duration=4, deadline=1)))["work"]
    assert result["date"] == DAYS[0] and result["startSlot"] == 28


def test_available_from_prevents_pulling_tomorrows_work_into_today(client):
    add(client, fixed("tomorrow-full", DAYS[1], 0, 32))
    result = all_items(add(client, task(day=DAYS[1], deadline_day=DAYS[2])))["work"]
    assert result["date"] == DAYS[2]
    assert client.get(f"/api/day/{DAYS[0]}").json()["items"] == []


def test_day_change_penalty_trades_off_against_move_count(client):
    for name, start, duration in [("short", 0, 1), ("long", 1, 3), ("medium", 4, 2)]:
        add(client, task(name, start=start, duration=duration))
    add(client, fixed("rest", DAYS[0], 6, 26))
    operation = {"type": "move", "itemId": "short", "targetStartSlot": 5}
    weights = {"movedTask": 10, "displacementSlot": 0, "largestDisplacementSlot": 0, "dayChange": 0}
    cheap = preview(client, operation, weights)
    assert cheap.status_code == 200
    assert all_items(cheap.json()["schedule"])["medium"]["date"] == DAYS[1]
    expensive = preview(client, operation, {**weights, "dayChange": 50})
    assert expensive.status_code == 200
    placed = all_items(expensive.json()["schedule"])
    assert placed["long"]["startSlot"] != 1
    assert placed["medium"]["startSlot"] != 4
    assert all(item["date"] == DAYS[0] for item in placed.values())


def test_future_day_edit_invalidates_source_day_preview(client):
    late_setup(client)
    plan = preview(client, {"type": "extend", "itemId": "late", "additionalSlots": 2}).json()
    add(client, fixed("changed-tomorrow", DAYS[1], 0, 1))
    before = saved(client)
    assert client.post("/api/optimizer/commit", json={"previewToken": plan["previewToken"]}).status_code == 409
    assert saved(client) == before


def test_new_task_options_can_be_on_different_dates_and_accept_exact_option(client):
    add(client, fixed("full", DAYS[0], 0, 32))
    response = client.post("/api/optimizer/proposals", json={"item": {
        "kind": "flexible", "id": "new", "title": "New", "date": DAYS[0], "durationSlots": 2,
        "deadlineSlot": 2, "deadlineDate": DAYS[2],
    }, "timeZone": "UTC"})
    assert response.status_code == 200, response.text
    options = response.json()
    assert all(option["date"] != DAYS[0] for option in options["alternatives"])
    chosen = options["alternatives"][-1]
    response = client.post(f'/api/optimizer/proposals/{options["proposalSetId"]}/accept', json={"alternativeId": chosen["id"]})
    assert response.status_code == 200
    assert response.json()["days"] == chosen["schedule"]["days"]
    assert all_items(response.json())["new"]["date"] == chosen["date"]


def test_explicit_move_to_another_date_preserves_id_and_duration(client):
    add(client, task(start=0))
    plan = preview(client, {"type": "move", "itemId": "work", "targetStartSlot": 0, "targetDate": DAYS[1]})
    assert plan.status_code == 200
    item = all_items(plan.json()["schedule"])["work"]
    assert (item["date"], item["durationSlots"]) == (DAYS[1], 2)
    assert preview(client, {"type": "move", "itemId": "work", "targetStartSlot": 0, "targetDate": DAYS[2]}).status_code == 409


def test_pinned_tasks_cannot_change_day(client):
    add(client, task(start=0, pinned=True))
    assert preview(client, {"type": "move", "itemId": "work", "targetStartSlot": 0, "targetDate": DAYS[1]}).status_code == 409


def test_elapsed_days_never_receive_automatic_moves(client):
    add(client, task(start=None, deadline_day=DAYS[2]))
    client.put("/api/demo/clock", json={"now": "2026-09-12T10:15:00"})
    result = add(client, task("new", day=DAYS[1], deadline_day=DAYS[2]))
    placed = all_items(result)
    assert placed["new"]["date"] >= DAYS[1]
    if placed["new"]["date"] == DAYS[1]:
        assert placed["new"]["startSlot"] >= 5
    assert placed["work"]["date"] == DAYS[0]  # Already-started history remains fixed.


def test_duration_beyond_one_day_is_rejected(client):
    assert client.post("/api/items", json=task(duration=33, deadline_day=DAYS[2])).status_code == 422


def test_editing_duration_can_move_task_to_future_day(client):
    add(client, fixed("busy", DAYS[0], 0, 30))
    original = task(start=30, duration=2, deadline=8)
    add(client, original)

    response = client.put("/api/items/work", json={**original, "durationSlots": 4})

    assert response.status_code == 200, response.text
    moved = all_items(response.json())["work"]
    assert (moved["date"], moved["startSlot"], moved["durationSlots"]) == (DAYS[1], 0, 4)
    assert [item["id"] for item in saved(client)[DAYS[0]]] == ["busy"]


def test_window_never_places_work_after_final_demo_day(client):
    add(client, fixed("full-last-day", DAYS[2], 0, 32))
    item = task(day=DAYS[2], deadline_day="2026-09-14")
    result = all_items(add(client, item))["work"]
    assert result["date"] == DAYS[2] and result["startSlot"] is None


def test_cross_day_undo_survives_backend_restart(client, tmp_path):
    late_setup(client)
    before = saved(client)
    plan = preview(client, {"type": "extend", "itemId": "late", "additionalSlots": 2}).json()
    assert client.post("/api/optimizer/commit", json={"previewToken": plan["previewToken"]}).status_code == 200
    with TestClient(create_app(tmp_path / "cross-day.sqlite3")) as restarted:
        assert restarted.post(f"/api/day/{DAYS[2]}/undo").status_code == 200
        assert saved(restarted) == before


def test_failed_destination_write_rolls_back_every_day_and_snapshot(client, monkeypatch):
    late_setup(client)
    before = saved(client)
    plan = preview(client, {"type": "extend", "itemId": "late", "additionalSlots": 2}).json()
    original_save = Repository._save

    def fail_on_destination(self, db, day, items, **kwargs):
        result = original_save(db, day, items, **kwargs)
        if day.isoformat() == DAYS[1]:
            raise RuntimeError("Simulated destination write failure")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Repository, "_save", fail_on_destination)
        with pytest.raises(RuntimeError, match="destination write failure"):
            client.post("/api/optimizer/commit", json={"previewToken": plan["previewToken"]})
    assert saved(client) == before
    assert all(not client.get(f"/api/day/{day}").json()["canUndo"] for day in DAYS)
    # The failed transaction must not consume the token or advance revisions.
    assert client.post("/api/optimizer/commit", json={"previewToken": plan["previewToken"]}).status_code == 200


def test_future_day_edit_invalidates_new_item_options(client):
    response = client.post("/api/optimizer/proposals", json={"item": {
        "kind": "flexible", "id": "new", "title": "New", "date": DAYS[0],
        "durationSlots": 2, "deadlineSlot": 32, "deadlineDate": DAYS[2],
    }, "timeZone": "UTC"})
    assert response.status_code == 200
    options = response.json()
    add(client, fixed("new-meeting", DAYS[2], 0, 1))
    before = saved(client)
    accepted = client.post(f'/api/optimizer/proposals/{options["proposalSetId"]}/accept',
        json={"alternativeId": options["alternatives"][0]["id"]})
    assert accepted.status_code == 409
    assert saved(client) == before
