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

- `GET /api/health`
- `GET /api/day/{date}`
- `POST /api/items?timeZone=America%2FNew_York` — add using unelapsed slots (default zone: UTC)
- `PUT /api/items/{id}`
- `PATCH /api/items/{id}`
- `DELETE /api/items/{id}`
- `POST /api/day/{date}/seed`
- `POST /api/optimizer/preview` — read-only move/extend proposal
- `POST /api/optimizer/commit` — save an unchanged, unexpired proposal token
- `POST /api/optimizer/proposals` — generate real CP-SAT alternatives for a new fixed event or flexible task
- `POST /api/optimizer/proposals/{id}/accept` — save one exact alternative and invalidate the set
- `POST /api/reschedule` — deprecated immediate extension compatibility route
- `POST /api/day/{date}/undo`

Use one API worker for the hackathon: preview tokens and proposal sets live in process memory for
up to 120 seconds. Calendars, revision counters, and Undo snapshots live in SQLite.
The [optimizer interface](../doc/optimizer.md#http-interface) documents payloads,
time-zone handling, conflict behavior, and stale-preview rejection.
