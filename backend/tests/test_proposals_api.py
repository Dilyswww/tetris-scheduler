import time

from fastapi.testclient import TestClient

from app.main import create_app
from test_api import DAY, fixed, flexible


def request_options(client, starts=(4, 6), duration=2):
    return client.post("/api/optimizer/proposals", json={
        "item": {
            "kind": "fixed",
            "id": "advisor-meeting",
            "title": "Advisor meeting",
            "date": DAY.isoformat(),
            "durationSlots": duration,
            "accent": "blue",
            "note": "",
        },
        "candidateStartSlots": list(starts),
        "timeZone": "UTC",
    })


def test_two_real_options_preview_without_writing_and_accept_exact_choice(tmp_path):
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        client.post("/api/items", json={**flexible(start_slot=4), "deadlineSlot": 16})
        client.post("/api/items", json={**flexible("other", start_slot=6), "deadlineSlot": 18})
        before = client.get(f"/api/day/{DAY}").json()

        response = request_options(client)
        assert response.status_code == 200
        proposal_set = response.json()
        assert len(proposal_set["alternatives"]) == 2
        assert {option["startSlot"] for option in proposal_set["alternatives"]} == {4, 6}
        assert client.get(f"/api/day/{DAY}").json() == before

        chosen = next(option for option in proposal_set["alternatives"] if option["startSlot"] == 6)
        saved = client.post(
            f'/api/optimizer/proposals/{proposal_set["proposalSetId"]}/accept',
            json={"alternativeId": chosen["id"]},
        )
        assert saved.status_code == 200
        assert saved.json()["items"] == chosen["schedule"]["items"]
        assert saved.json()["changes"] == chosen["schedule"]["changes"]
        assert saved.json()["canUndo"] is True
        assert client.post(
            f'/api/optimizer/proposals/{proposal_set["proposalSetId"]}/accept',
            json={"alternativeId": chosen["id"]},
        ).status_code == 409
        assert client.post(f"/api/day/{DAY}/undo").json()["items"] == before["items"]


def test_infeasible_candidate_is_omitted_and_all_infeasible_is_rejected(tmp_path):
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        client.post("/api/items", json={**flexible("gym", start_slot=4), "isPinned": True, "deadlineSlot": 20})
        response = request_options(client)
        assert response.status_code == 200
        assert [option["startSlot"] for option in response.json()["alternatives"]] == [6]
        assert request_options(client, (4, 5)).status_code == 409


def test_stale_or_expired_proposal_set_cannot_write(tmp_path, monkeypatch):
    moment = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: moment[0])
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        stale = request_options(client).json()
        client.post("/api/items", json=fixed("other-change", start_slot=10))
        chosen = stale["alternatives"][0]
        assert client.post(
            f'/api/optimizer/proposals/{stale["proposalSetId"]}/accept',
            json={"alternativeId": chosen["id"]},
        ).status_code == 409

        expiring = request_options(client, (12, 14)).json()
        moment[0] = 121
        assert client.post(
            f'/api/optimizer/proposals/{expiring["proposalSetId"]}/accept',
            json={"alternativeId": expiring["alternatives"][0]["id"]},
        ).status_code == 409


def test_proposal_request_validation(tmp_path):
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        single = request_options(client, (4,))
        assert single.status_code == 200
        assert [option["startSlot"] for option in single.json()["alternatives"]] == [4]
        assert request_options(client, (4, 4)).status_code == 422
        assert request_options(client, (1, 2), duration=32).status_code == 409


def test_flexible_task_gets_two_distinct_solver_generated_options(tmp_path):
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        client.post("/api/items", json={**flexible("existing", start_slot=0), "deadlineSlot": 20})
        before = client.get(f"/api/day/{DAY}").json()
        response = client.post("/api/optimizer/proposals", json={
            "item": {
                "kind": "flexible",
                "id": "new-work",
                "title": "New work",
                "date": DAY.isoformat(),
                "durationSlots": 2,
                "deadlineSlot": 12,
                "accent": "purple",
                "note": "",
            },
            "timeZone": "UTC",
        })
        assert response.status_code == 200
        proposal_set = response.json()
        assert len(proposal_set["alternatives"]) == 2
        starts = {option["startSlot"] for option in proposal_set["alternatives"]}
        assert len(starts) == 2
        for option in proposal_set["alternatives"]:
            task = next(item for item in option["schedule"]["items"] if item["id"] == "new-work")
            assert task["kind"] == "flexible"
            assert task["startSlot"] == option["startSlot"]
            assert task["startSlot"] + task["durationSlots"] <= task["deadlineSlot"]
        assert client.get(f"/api/day/{DAY}").json() == before


def test_flexible_task_returns_one_option_when_only_one_start_is_possible(tmp_path):
    with TestClient(create_app(tmp_path / "proposals.sqlite3")) as client:
        response = client.post("/api/optimizer/proposals", json={
            "item": {
                "kind": "flexible", "id": "tight", "title": "Tight task",
                "date": DAY.isoformat(), "durationSlots": 2, "deadlineSlot": 2,
                "accent": "purple", "note": "",
            },
            "timeZone": "UTC",
        })
        assert response.status_code == 200
        assert [option["startSlot"] for option in response.json()["alternatives"]] == [0]
