# Tetris — HackCMU 2026

Tetris helps people adapt their daily calendar when plans change. Fixed events
and pinned tasks stay in place; flexible tasks fit around them before their
deadlines. Each day runs from 8 AM to midnight in 30-minute slots.

## Quick start

With mise installed, run these commands from the **repository root**:

```sh
mise install
mise exec -- npm --prefix frontend ci
mise run frontend
```

Open the local address printed by Vite, normally `http://localhost:5173`.
Press `Ctrl+C` in the terminal to stop the server.

[mise.toml](mise.toml) selects Node 24.19.0, Python 3.12, and uv. The current
frontend only requires Node/npm; Python and uv are for the planned backend.
Mise manages tool versions, while uv will manage Python dependencies and the
backend virtual environment.

## Build, run, and test commands

All commands in this table run from the **repository root**.

| Action | Command |
| --- | --- |
| Install configured tools | `mise install` |
| Install frontend dependencies from the lockfile | `mise exec -- npm --prefix frontend ci` |
| Start the frontend with hot reload | `mise run frontend` |
| Type-check and build the frontend | `mise run frontend-build` |
| Run scheduler tests | `mise exec -- npm --prefix frontend test` |
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

Phase 1 runs entirely in the frontend:

- React + TypeScript + Vite calendar and task-list views.
- Create and delete fixed events and flexible tasks.
- Pin and unpin items.
- First-fit placement that protects fixed/pinned items and respects deadlines.
- Full-day scrolling and live schedule totals.

The app loads a sample day. Changes are held in React state and **reset on
refresh**. No API keys, backend service, or database are required to run it.

FastAPI, the Python scheduler, and SQLite persistence are planned. Delay
handling, movement optimization, deferral, and Undo are still pending.
Google Calendar and sponsor integrations are optional later work.

## Project layout

```text
frontend/          React app, placeholder scheduler, and tests
doc/               Execution plan and project documentation
mise.toml          Development tool versions and task shortcuts
AGENT.md           Project brief, constraints, and implementation phases
```

The planned `backend/` directory will contain FastAPI, persistence, and the
Python scheduler. Backend build/run commands will be added here when that
service is implemented.

See the [execution plan](doc/execution-plan.md) for the eight-hour build scope
and the [frontend notes](frontend/README.md) for the source map, scheduler
limitations, and manual demo checks.
