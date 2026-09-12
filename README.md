# Tetris — HackCMU 2026

Tetris helps people adapt their daily calendar when plans change. Fixed events
and pinned tasks stay in place; flexible tasks fit around them before their
deadlines. Each day runs from 8 AM to midnight in 30-minute slots.

## Quick start

With mise installed, run these commands from the **repository root**:

```sh
mise trust
mise install
mise exec -- npm --prefix frontend ci
mise run backend-sync
```

Start the two development servers in separate terminals:

```sh
mise run backend
```

```sh
mise run frontend
```

Open the frontend address printed by Vite, normally `http://localhost:5173`.
FastAPI listens at `http://127.0.0.1:8000`; its API documentation is at
`http://127.0.0.1:8000/docs`. Press `Ctrl+C` in each terminal to stop the
servers.

[mise.toml](mise.toml) selects Node 24.19.0, Python 3.12, and uv. Mise manages
tool versions; npm manages frontend packages and uv manages Python packages in
`backend/.venv`.

## Build, run, and test commands

All commands in this table run from the **repository root**.

| Action | Command |
| --- | --- |
| Trust this repository's mise configuration | `mise trust` |
| Install configured tools | `mise install` |
| Install frontend dependencies from the lockfile | `mise exec -- npm --prefix frontend ci` |
| Install backend dependencies from the lockfile | `mise run backend-sync` |
| Start the frontend with hot reload | `mise run frontend` |
| Start FastAPI with hot reload | `mise run backend` |
| Type-check and build the frontend | `mise run frontend-build` |
| Type-check the frontend | `mise exec -- npm --prefix frontend test` |
| Run backend API and scheduler tests | `mise run backend-test` |
| Preview the production build locally | `mise exec -- npm --prefix frontend run preview` |

The build writes to `frontend/dist/`. Run the build before starting a production
preview, then open the address printed by Vite. Both dev and preview servers
keep running until stopped with `Ctrl+C`.

If the configured Node version is already on your PATH, the equivalent npm
commands are:

```sh
npm --prefix frontend ci
npm --prefix frontend run dev
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend run preview
```

Run each command as needed; stop the development server before continuing in
the same terminal, or use another terminal for builds and tests.

Keep this command reference updated when adding or changing scripts in
`frontend/package.json`, tasks in `mise.toml`, or backend entry points.

## Current state

Phase 1 is implemented across the frontend and backend:

- React + TypeScript + Vite calendar and task-list views.
- Create and delete fixed events and flexible tasks.
- Pin and unpin items.
- FastAPI and SQLite persistence across browser refreshes.
- Python first-fit placement that protects fixed/pinned items and respects
  deadlines.
- Full-day scrolling and live schedule totals.

An empty day can be filled with sample data from the interface. The backend
creates its SQLite database at `backend/data/tetris.sqlite3` on first start.
No API keys or external services are required.

Delay handling, movement optimization, deferral, and Undo are still pending.
Google Calendar and sponsor integrations are optional later work.

## Project layout

```text
frontend/          React interface and API client
backend/           FastAPI service, Python scheduler, SQLite repository, tests
doc/               Execution plan and project documentation
mise.toml          Development tool versions and task shortcuts
AGENT.md           Project brief, constraints, and implementation phases
```

See the [execution plan](doc/execution-plan.md) for the eight-hour build scope
and the [frontend notes](frontend/README.md) for the source map, scheduler
limitations, and manual demo checks. Backend details are in
[backend/README.md](backend/README.md).
