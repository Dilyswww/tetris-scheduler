# Tetris backend

The backend is a FastAPI service backed by SQLite. It owns calendar validation,
placement, and persistence. The frontend reaches it through Vite's `/api`
development proxy.

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
- `POST /api/items`
- `PATCH /api/items/{id}`
- `DELETE /api/items/{id}`
- `POST /api/day/{date}/seed`
