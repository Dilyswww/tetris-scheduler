from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_api import DAY, fixed, flexible


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "add.sqlite3")) as client:
        yield client


@pytest.mark.parametrize("minute,second,expected", [(0, 0, 4), (0, 1, 5), (15, 0, 5), (30, 0, 5)])
def test_add_rounds_up_using_client_timezone(client, frozen_clock, minute, second, expected):
    frozen_clock[0] = datetime(2026, 9, 12, 14, minute, second, tzinfo=timezone.utc)
    # 14:xx UTC is 10:xx AM in New York. Even a supplied past start is rescheduled.
    response = client.post("/api/items?timeZone=America%2FNew_York", json=flexible(start_slot=0))
    assert response.status_code == 201
    assert response.json()["items"][0]["startSlot"] == expected


def test_add_preserves_started_work_and_does_not_fill_elapsed_gaps(client, frozen_clock):
    client.post("/api/items", json=flexible("done", start_slot=0))
    client.post("/api/items", json=flexible("ongoing", start_slot=4))
    before = client.get(f"/api/day/{DAY}").json()["items"]
    frozen_clock[0] = datetime(2026, 9, 12, 10, 15, tzinfo=timezone.utc)
    response = client.post("/api/items", json=flexible("new"))
    assert response.status_code == 201
    assert response.json()["items"][:2] == before
    assert response.json()["items"][2]["startSlot"] == 6


@pytest.mark.parametrize("hour,minute,deadline", [(10, 15, 6), (23, 45, 32)])
def test_add_defers_when_remaining_time_is_insufficient(client, frozen_clock, hour, minute, deadline):
    frozen_clock[0] = datetime(2026, 9, 12, hour, minute, tzinfo=timezone.utc)
    response = client.post("/api/items", json={**flexible(), "deadlineSlot": deadline})
    assert response.status_code == 201
    assert response.json()["items"][0]["startSlot"] is None


@pytest.mark.parametrize("item", [fixed(start_slot=4), {**flexible(start_slot=4), "isPinned": True}])
def test_add_rejects_protected_past_start_atomically(client, frozen_clock, item):
    frozen_clock[0] = datetime(2026, 9, 12, 10, 15, tzinfo=timezone.utc)
    response = client.post("/api/items", json=item)
    assert response.status_code == 409
    assert client.get(f"/api/day/{DAY}").json()["items"] == []


def test_adding_fixed_event_cannot_push_flexible_work_into_past(client, frozen_clock):
    client.post("/api/items", json=flexible(start_slot=6))
    frozen_clock[0] = datetime(2026, 9, 12, 10, 15, tzinfo=timezone.utc)
    response = client.post("/api/items", json=fixed(start_slot=6))
    assert response.status_code == 201
    assert response.json()["items"][0]["startSlot"] == 8


def test_future_days_and_before_day_start_allow_slot_zero(client, frozen_clock):
    frozen_clock[0] = datetime(2026, 9, 12, 7, tzinfo=timezone.utc)
    assert client.post("/api/items", json=flexible()).json()["items"][0]["startSlot"] == 0
    frozen_clock[0] = datetime(2026, 9, 12, 23, tzinfo=timezone.utc)
    tomorrow = {**flexible("tomorrow"), "date": "2026-09-13"}
    assert client.post("/api/items", json=tomorrow).json()["items"][0]["startSlot"] == 0


def test_add_rejects_invalid_timezone_and_past_day(client, frozen_clock):
    assert client.post("/api/items?timeZone=Invalid%2FZone", json=flexible()).status_code == 409
    frozen_clock[0] = datetime(2026, 9, 13, 8, tzinfo=timezone.utc)
    assert client.post("/api/items", json=flexible()).status_code == 409
    assert client.get(f"/api/day/{DAY}").json()["items"] == []
