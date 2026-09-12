# Tetris backend

The backend is a FastAPI service backed by SQLite. It owns calendar validation,
CP-SAT placement, rescheduling, Undo snapshots, and persistence. The frontend
reaches it through Vite's `/api` development proxy. See the
[optimizer design](../doc/optimizer.md) for variables, constraints, objective
priorities, and transaction behavior.

From the repository root:

```sh
mise run backend-sync
mise run backend
```

The API listens at `http://127.0.0.1:8000`; interactive OpenAPI documentation
is at `http://127.0.0.1:8000/docs`. The database is created on first start at
`backend/data/tetris.sqlite3` and is ignored by Git.

Run the backend suite with `mise run backend-test`. Set `TETRIS_DB_PATH` to use
a different SQLite file.

Routes:

- `POST /api/demo/start` — initialize the shared paused presentation clock
- `GET /api/demo/clock` — read the clock and revision
- `PUT /api/demo/clock` — set a New York local timestamp within September 11–13
- `GET /api/health`
- `GET /api/day/{date}`
- `POST /api/items?timeZone=America%2FNew_York` — add using unelapsed slots (default zone: UTC)
- `PUT /api/items/{id}`
- `PATCH /api/items/{id}`
- `DELETE /api/items/{id}`
- `POST /api/day/{date}/seed`
- `POST /api/debug/reset?day=2026-09-11` — replace all three demo days with the deterministic debug fixture
- `POST /api/optimizer/preview` — read-only move/extend/edit proposal
- `POST /api/optimizer/commit` — save an unchanged, unexpired proposal token
- `POST /api/optimizer/proposals` — generate real CP-SAT alternatives for a new fixed event or flexible task
- `POST /api/optimizer/proposals/{id}/accept` — save one exact alternative and invalidate the set
- `POST /api/reschedule` — deprecated immediate extension compatibility route
- `POST /api/day/{date}/undo`

The [three-day demo guide](../doc/demo.md) documents clock payloads and behavior.
The clock is stored in SQLite. All previews record its revision and reject commit
after it changes; saved schedules and the shared three-day Undo remain intact.
Scheduling reads all three dates, checks each revision, and saves the complete
window in one transaction. Flexible tasks use `earliestDate`/`deadlineDate`
bounds and pay a configurable `dayChange` penalty (default 24 per day crossed).
Each task remains one continuous interval within a day. Window responses include
`days`; top-level `items` still represents the requested/source day.

The debug reset is intentionally destructive and intended for this hackathon
demo. It atomically replaces items on September 11–13, clears the shared Undo
snapshot, increments all three revisions so pending previews become stale, and
leaves the demo clock unchanged. Calling it again produces the same item IDs and
placements.

Use one API worker for the hackathon: preview tokens and proposal sets live in process memory for
up to 120 seconds. Calendars, revision counters, and Undo snapshots live in SQLite.
The [optimizer interface](../doc/optimizer.md#http-interface) documents payloads,
time-zone handling, conflict behavior, and stale-preview rejection.
