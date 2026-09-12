from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Scheduling tests must not depend on the time the suite is run."""
    moment = [datetime(2026, 9, 12, 8, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.repository.utc_now", lambda: moment[0])
    return moment
