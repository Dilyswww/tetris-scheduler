# Tetris frontend — Phase 1

See the [root README](../README.md#build-run-and-test-commands) for setup,
development, build, test, and preview commands. That is the shared command
reference for the project.

The scheduler tests use Node 24's built-in TypeScript support; no additional
test dependency is required.

## Implemented

- Scrollable 8 AM–midnight calendar with 32 half-hour slots.
- Fixed events with start/end times; flexible tasks with duration/deadline.
- Add, delete, pin, and unpin through forms and item details.
- A task list, live planned/free-time totals, and a real current-time marker.
- Atomic additions: protected conflicts or placement failures show an error
  without changing the existing day.

The app starts with a sample schedule on today's local date. Calendar changes
are held in React state and reset on refresh. There is no backend or database
connection yet.

## Source map

- `src/types.ts`: shared item types. Slot 0 starts at 8 AM; boundary 32 is
  midnight. Deadlines are inclusive of finishing at that boundary. Pinning is
  a property of either kind of item.
- `src/seed.ts`: sample schedule, kept separate from the UI.
- `src/scheduler.ts`: pure, temporary frontend placement function. It reserves
  fixed/pinned items, preserves valid flexible placements, then assigns new
  or displaced tasks to the first continuous gap before their deadlines.
- `src/App.tsx`: calendar/list views and state updates.
- `src/ItemForm.tsx` and `src/Dialog.tsx`: creation and accessible modal controls.

This greedy placeholder can reject a day that a more complete optimizer could
solve by moving additional tasks. It does not split tasks, enforce a moving
"now" cutoff, or provide delay handling, deferral, or Undo. The planned Python
scheduler will become the authority when the FastAPI backend is connected.

## Manual demo check

1. Add a flexible task with a 30-minute duration and a 5 PM deadline. It should
   fill the earliest available half-hour while existing placements stay put.
2. Open the new task, pin it, and close the dialog. Its card should say Pinned.
3. Try adding a fixed event at that task's time. The form should report the
   protected conflict and leave the day unchanged.
4. Cancel, unpin the task, and retry. The flexible task should move to a free
   gap; the status message should identify the move.
5. Open either item and delete it. Check the Tasks view and free-time total.
6. Scroll to Gym at 6 PM, Read at 8 PM, and the midnight boundary. The timeline
   and time labels should scroll together. Also check a narrow phone viewport.

Automated scheduling checks and the production build pass. Browser interaction
and visual checks still need to be run when a browser is available.
