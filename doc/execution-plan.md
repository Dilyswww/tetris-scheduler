# Tetris execution plan

## Goal

Build a single-day calendar that keeps a realistic plan when a task runs late.
The demo must show fixed events, flexible tasks, pinned items, an automatic
reschedule with minimal disruption, an explanation of the changes, and Undo.

The schedule runs from 8:00 AM to 12:00 AM in unbreakable 30-minute slots.

## Implementation status

Phase 1 is implemented: task types, full-day calendar, adding/deleting fixed and
flexible items, pin/unpin, FastAPI, SQLite persistence, and the Python CP-SAT
scheduler. See the [frontend](../frontend/README.md) and
[backend](../backend/README.md) handoffs for details.

Phase 2's drag-to-time and delay handling, CP-SAT movement optimization, deferral,
structured previews, validated commits, and one-level Undo are implemented. See
[optimizer.md](optimizer.md) for the operation and API contracts. Multi-day scheduling
and optional integrations remain pending.

## Scope for the eight-hour hackathon

### Required MVP

- Day calendar with 30-minute slots.
- Create and delete fixed events and flexible tasks.
- Give each flexible task a duration and deadline.
- Pin any item so the scheduler cannot move it.
- Extend the current item or report that the user is running late.
- Reschedule only the necessary flexible tasks.
- Show moved and deferred tasks, including a concise reason for each change.
- Undo the most recent reschedule.

### Only if the MVP is complete

- Gemini-powered text input, such as: "My 2 PM meeting ran 45 minutes late; keep gym."
- Gemini-generated, human-readable summary of the deterministic schedule result.
- Deploy the app on Vultr.
- Google Calendar read/sync integration.

Do not spend hackathon time on authentication, mobile native applications,
Apple Calendar/CalDAV, blockchain, or a production-grade multi-user system.

## Technical design

### Frontend

Use React, TypeScript, and Vite. Build a custom day-grid rather than adapting
a general calendar library: the product has one day, a fixed 30-minute grid,
and special scheduling interactions.

Frontend responsibilities:

- Render the calendar, task form, detail panel, and change summary.
- Make actions explicit: add, pin/unpin, extend by 30 minutes, undo.
- Call the FastAPI backend for persisted data and rescheduling.
- Visually distinguish fixed, flexible, pinned, moved, and deferred items.

### Backend and persistence

Use FastAPI with Pydantic models and SQLite. SQLite avoids hosted database
setup while preserving the demo state across page refreshes. Keep storage
behind a small repository layer so it can later move to MongoDB Atlas if that
becomes useful.

Suggested routes:

- `GET /api/day/{date}`: calendar items and the current schedule.
- `POST /api/items`: create a fixed event or flexible task.
- `PATCH /api/items/{id}`: pin/unpin an item.
- `PUT /api/items/{id}`: edit an item.
- `DELETE /api/items/{id}`: remove an item.
- `POST /api/optimizer/preview`: preview a move or extension without saving.
- `POST /api/optimizer/commit`: commit an unexpired preview if the day is unchanged.
- `POST /api/day/{date}/undo`: restore the previous schedule snapshot.

### Scheduler

Keep the scheduler as a pure Python module. It receives the day's items and a
change request, then returns a proposed schedule, a list of moves, and any
deferred tasks. The API layer saves that result; it must not contain the
scheduling decisions.

Scheduling rules:

1. Divide the day into 32 slots, from 8:00 AM through midnight.
2. Protect fixed, pinned, and already-started items during move/extend operations.
3. Lock a dragged task at the chosen start, or extend a selected item's duration
   while keeping its start unchanged.
4. Require other placements to use unelapsed time and finish by their deadlines.
5. Use CP-SAT to minimize deferred tasks, then moved tasks, then total absolute
   displacement, with scheduling preferences as the final tie-breaker.
6. Return proposed placements and explanations without changing the saved day.
7. On commit, validate the revision and time boundary, save the pre-change
   schedule as the single Undo snapshot, and persist the exact proposal atomically.

## Build sequence

### Hour 0–0.5: scaffold and seed data

- Create `frontend`, `backend`, and `doc` directories.
- Scaffold the React/Vite app and FastAPI service.
- Define shared item concepts and API payloads.
- Add a seeded day that makes the rescheduling story immediately visible.

### Hour 0.5–2.5: interactive calendar

- Implement the day-grid and item cards.
- Add forms for fixed events and flexible tasks.
- Support item deletion and pinning.
- Use local state first if necessary; connect persistence as soon as the UI
  flow is clear.

### Hour 2.5–4: backend and basic placement

- Add SQLite models and the CRUD endpoints.
- Implement a basic first-fit placement algorithm for flexible tasks.
- Connect frontend CRUD operations to the backend.

### Hour 4–6: rescheduling and Undo

- Implement extension/running-late requests.
- Add the stability-first movement rules and deferred-task state.
- Record a structured change list and one schedule snapshot.
- Build the visible change summary and Undo action.

### Hour 6–7: polish the demo narrative

- Improve task colors, pin state, transitions, and empty/error states.
- Add a preset scenario: an afternoon meeting runs 30 minutes late and moves
  a slide-preparation task while preserving a pinned gym session.
- Confirm every action has clear feedback.

### Hour 7–8: optional sponsor integration and verification

- If the core flow is complete, add a Gemini text command that maps a user
  message to the existing reschedule request schema. Validate its output and
  fall back to the regular controls on failure.
- If deployment is required, deploy the finished application to Vultr.
- Rehearse the demo from a fresh browser session.

## Sponsor technology decision

Use Gemini only as an optional input and explanation layer. The deterministic
scheduler remains the authority on calendar changes, which prevents surprising
or invalid AI results.

Use Vultr for deployment only after the local demo is reliable. Auth0 and
MongoDB Atlas are not part of the MVP because they increase setup time without
improving the core demonstration. ElevenLabs and Solana do not support the
main product story closely enough to justify their cost in build time.

## Demo script

1. Show the day with a fixed 2:00 PM meeting, flexible slide preparation, and
   a pinned 6:00 PM gym session.
2. Mark the meeting as 30 minutes late.
3. Show the change panel: slide preparation moves to the nearest valid gap,
   while gym stays fixed because it is pinned.
4. Show a task deferred if the calendar cannot accommodate it.
5. Press Undo to restore the initial plan.
6. If available, repeat the delay using Gemini natural-language input.
