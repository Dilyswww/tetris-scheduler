# Optimizer: drag a task or extend an item

The optimizer schedules one local calendar day, 8 AM–midnight, using 32
indivisible 30-minute slots. Slot 0 means 8 AM; end boundary 32 means midnight.
Intervals are half-open: `[startSlot, startSlot + durationSlots)`. Tasks cannot
split or cross days. OR-Tools CP-SAT owns placement decisions.

## Two operations, one solver

| Rule | Move / drag | Extend / running late |
| --- | --- | --- |
| User intent | Reserve a particular start time | Reserve more time at the existing start |
| Selected item | Unpinned flexible task, including a deferred task through Move task | Any scheduled item, including fixed or pinned |
| Required placement | Exactly `targetStartSlot` | Original start |
| Required duration | Original duration | Original duration plus 1–4 slots (30–120 minutes) |
| Can the selected item defer? | No | No |
| Can other flexible tasks move earlier? | Yes, into time that has not elapsed, including the vacated slot | Yes, if that time has not elapsed |
| Protected work | Fixed, pinned, and already-started items other than the explicitly moved target | Fixed, pinned, and already-started items other than the explicitly extended target |

These actions have different feasibility constraints, rather than competing
versions of the same placement preference. A drag's chosen start is mandatory;
a penalty must never let the solver ignore the drop. An extension changes how
much time is available while preserving its start.

Both use the same objective for **collateral changes**, in strict priority order:

1. Minimize the number of deferred flexible tasks.
2. Minimize the number of other previously scheduled tasks whose start changes.
3. Minimize their total absolute start-time displacement, measured in slots.
4. Prefer earlier placements; for deferral ties, prefer preserving tasks with
   earlier deadlines and older positions in the day's item list.

The requested move itself is excluded from collateral movement cost by locking
the target at its requested placement before optimization. Deferred tasks count
in tier 1; they have no displacement. Newly placed tasks have no previous start
and therefore no movement penalty. Task priority, forward-only shifting, order
preservation, and schedule compression are not separate objectives in this MVP.

Example before 8 AM: A occupies slots 0–2 and B occupies 2–4. Drag A to slot 2:
B can move into the vacated 0–2 gap. Extend A by two slots instead: A occupies
0–4, so B must go elsewhere, such as 4–6. The objective is shared; the feasible
placements differ.

## Time and protection rules

Requests supply an IANA `timeZone`, such as `America/New_York`. The server
uses its own clock, not a client-supplied “now.”

- For today, `earliestStartSlot` is the current local time rounded up to the
  next slot boundary, clamped to 0–32. At 10:15 AM this is slot 5, or 10:30 AM.
- For future days, it is 0. Past days cannot be adjusted.
- Every non-target item whose original start is less than this boundary is
  locked in place. This includes completed and in-progress work.
- Other movable tasks must start at or after this boundary.
- A move cannot target elapsed time. An unpinned flexible task whose planned
  start has passed may be explicitly moved to an unelapsed slot; this models
  work the user intended to do earlier but did not complete.
- The selected extended item may retain an elapsed start. Its new end must
  reach the current time or later and remain within its deadline/day.
- Fixed or pinned blockers are never silently moved, even if a selected
  extension overlaps them. That request is rejected.

There is no explicit completion or “actually started” field yet. Conservatively
freezing all other started calendar entries can reject a late extension that
crosses another entry whose planned start has passed, even if the user has not
actually begun that entry. A user-selected unpinned flexible task is the one
exception: it can be moved out of the past into a future slot. Explicit execution
state would be a future enhancement.

These time rules apply to optimizer move/extend operations and adding items.
New flexible tasks can only use unelapsed slots; if no future gap fits their
duration and deadline, they are deferred. Existing started items stay locked
during additions. New fixed or pinned items with elapsed starts are rejected.
Ordinary edit/delete/pin placement remains the existing whole-day planning behavior. Undo
restores the exact prior snapshot, even if time has since advanced.

## HTTP interface

All JSON fields use camelCase. Request objects reject unknown fields and require
integer slot values. The routes are also described in FastAPI's `/docs`.

### Add: `POST /api/items?timeZone=America%2FNew_York`

The body remains a `CalendarItem`. The optional `timeZone` query parameter
defaults to UTC for existing API clients; the frontend always sends the browser's
IANA time zone. The server computes the earliest start using its current clock.
At 10:15 AM, the first eligible start is 10:30 AM. A supplied past start on an
unpinned flexible task is rescheduled; a fixed or pinned past start returns
`409`. Past calendar dates are rejected, future dates can start at 8 AM, and
tasks that cannot fit in today's remaining time are saved as deferred.

### Preview: `POST /api/optimizer/preview`

Drag / choose a time:

```json
{
  "operation": {
    "type": "move",
    "itemId": "write-report",
    "targetStartSlot": 12
  },
  "timeZone": "America/New_York"
}
```

Running late:

```json
{
  "operation": {
    "type": "extend",
    "itemId": "client-meeting",
    "additionalSlots": 2
  },
  "timeZone": "America/New_York"
}
```

| Field | Contract |
| --- | --- |
| `operation.type` | Discriminator: `move` or `extend` |
| `operation.itemId` | Existing item ID; determines which day is optimized |
| `targetStartSlot` | Required only for move; integer 0–31; full duration must fit by the deadline |
| `additionalSlots` | Required only for extend; integer 1–4 |
| `timeZone` | Required IANA time-zone identifier |

Successful response, using TypeScript notation to show the exact shape:

```ts
type SchedulePreview = {
  previewToken: string;
  expiresInSeconds: 120;
  operation:
    | { type: "move"; itemId: string; targetStartSlot: number }
    | { type: "extend"; itemId: string; additionalSlots: number };
  earliestStartSlot: number; // 0–32
  schedule: DaySchedule;
};

type DaySchedule = {
  date: string; // YYYY-MM-DD
  items: CalendarItem[]; // Complete proposed day, including deferred items
  changes: ScheduleChange[];
  canUndo: boolean;
  solverStatus: "optimal" | "feasible" | null;
};

type ScheduleChange = {
  itemId: string;
  title: string;
  changeType: "extended" | "moved" | "deferred" | "scheduled" | "restored";
  fromStartSlot: number | null;
  toStartSlot: number | null;
  fromDurationSlots: number | null;
  toDurationSlots: number | null;
  reason: string;
};
```

`CalendarItem` retains the existing fixed/flexible union: ID, title, local date,
kind, start, duration, pin flag, accent, note, and a deadline for flexible tasks.
A deferred flexible task has `startSlot: null`; its duration and deadline remain
unchanged. The selected target appears first in `changes`; other records appear
in saved item order. Unchanged items have no record. The selected drag target
uses `moved`, including when it previously had no placement.

Preview writes **nothing to SQLite**. It neither creates nor replaces Undo.
The nested `canUndo` describes the currently saved day's existing snapshot;
it does not imply that the proposal was applied. Preview reasons describe the
chosen plan, not a formal proof that a particular task has no possible placement
in every alternative plan.

### Commit: `POST /api/optimizer/commit`

```json
{
  "previewToken": "<token returned by preview>"
}
```

The response is a saved `DaySchedule` with `canUndo: true`. Its items, changes,
and solver status match the accepted preview exactly. The client does not
submit a replacement schedule, and commit does not solve again.

1. Find the server-held proposal and validate its 120-second lifetime.
2. Open a SQLite write transaction.
3. Confirm the day's revision still matches the preview's revision.
4. Recompute the time boundary in the original request's time zone. If it
   changed, require a fresh preview.
5. Store the current day as its single Undo snapshot.
6. Save the exact proposal, increment the day revision, and commit atomically.
7. Consume the token.

Any successful add, edit, delete, pin, seed, optimizer commit, or Undo increments
the revision. Thus a preview becomes stale even if later edits or Undo restore
identical item values. Reusing a committed token cannot apply the change twice.
Failed operations do not modify the day or its snapshot.

### Multiple new-item options

`POST /api/optimizer/proposals` accepts an unsaved fixed-event or flexible-task
draft and an IANA time zone. Fixed events include one to four distinct candidate
start slots; each is locked in turn and solved by CP-SAT. For flexible tasks,
CP-SAT first finds the best required placement, then solves again while excluding
that start to produce the best distinct alternative. If only one start is
feasible, one option is returned. All solves use the same saved-day revision and
time boundary. Infeasible options are omitted; a `409` is returned only when no
placement is feasible. The response contains a temporary `proposalSetId` and the
real schedule, structured changes, and disruption metrics for each option.
Generating or switching options never writes to SQLite.

`POST /api/optimizer/proposals/{proposalSetId}/accept` accepts an
`alternativeId`. It validates the set's 120-second lifetime, revision, and time
boundary, stores the current schedule as the Undo snapshot, and persists the
exact selected schedule without solving again. Accepting one alternative
invalidates the entire set, so another option cannot be applied afterward.
The client never submits a replacement schedule.

### Undo: `POST /api/day/{date}/undo`

Restores the exact saved item payloads, returns `restored` change records, clears
the one-level snapshot, and increments the revision. Undo persists across app
restarts. A new optimizer commit replaces the previous snapshot; a successful
add/edit/delete/pin clears it. Preview and failed requests preserve it.

### Errors

| Status | Meaning |
| --- | --- |
| `404` | Selected item no longer exists |
| `409` | Protected overlap, elapsed/past time, invalid time zone, unchanged move, invalid target kind, deadline/day overflow, stale/expired/unknown token, or no Undo snapshot |
| `422` | Invalid request structure, discriminator, slot range, or field type |
| `503` | Solver reached its limit without finding a usable solution |

Domain errors return `{ "detail": "Human-readable explanation" }`. Standard
FastAPI validation errors have a structured `detail` array. Overloaded flexible
work is deferred in a successful proposal; the entire request fails only when
required constraints cannot be honored or no usable solution is found.

### Compatibility route

`POST /api/reschedule` is deprecated. It accepts
`{ itemId, additionalSlots, timeZone? }` (legacy default time zone: UTC), runs
the same extend preview internally, and commits immediately. The frontend uses
the explicit preview/commit interface.

## Frontend behavior

**Drag:** Desktop calendar cards for eligible flexible tasks are draggable.
Hover positions snap to half-hour slots, accounting for where the card was
grabbed. After 150 ms at a target, the client requests a preview. Proposed card
positions, dashed outlines, and the change list show the result without updating
saved state. Invalid targets show an error. Drop commits only a ready proposal
for that exact target; releasing outside the calendar or Escape cancels. If no
valid proposal is ready, no changes are saved. Edge hovering scrolls the day.

**Move task:** The item's detail dialog also offers a time selector with the
same preview and Apply flow, for keyboard and touch use and deferred tasks.

**Running late:** Choose an item and 30–120 extra minutes. The dialog previews
moved and deferred items automatically. Apply commits that proposal; Cancel
leaves the day untouched.

Changed inputs cancel obsolete requests, and response keys prevent older
responses from replacing the current target's preview. Apply disables repeat
submission. Commit failure leaves saved state unchanged; the dialog requests
a new preview. If the calendar changed elsewhere, reload it before continuing.
After either commit, the shared change panel exposes Undo.

## Python solver interface and model

```python
schedule_items(
    source: Sequence[CalendarItem],
    *,
    locked_ids: frozenset[str] = frozenset(),
    earliest_start_slot: int = 0,
    time_limit_seconds: float = 0.5,
) -> SolverResult
```

This function copies its inputs. `SolverResult` contains `items`, `status`
(`optimal` or `feasible`), and the integer `objective_value`.
The repository translates the operation into an adjusted target, a lock set,
and a time boundary; builds explanations against the original day; and owns
preview/commit/Undo. The solver performs no storage or HTTP work.

For each valid start the solver creates a Boolean `place[item, start]`.
Every unprotected flexible task also gets `deferred[item]`. Exactly one
placement or deferral is selected per item, and at most one selected interval
covers any slot. Fixed, pinned, and explicitly locked items have only their
required start and cannot defer. All scheduled tasks finish by their deadline.

One integer objective encodes the four priority tiers. Each weight exceeds the
maximum total cost of all lower tiers, so one fewer deferred task always beats
any movement improvements, and one fewer moved task always beats any displacement
improvements. Fixed placements contribute only constant costs.

Saved placements are solution hints. The solver uses one worker, a fixed seed,
and a 500 ms limit. `optimal` proves the objective minimum; `feasible` means a
valid incumbent was found without proving optimality. Time limits and tied
solutions mean this is not a guarantee of identical outputs across runs.

## Hackathon limits and verification

Preview tokens are random opaque IDs held only in the API process, capped at
256 proposals. Expired tokens, evicted tokens, and tokens from a previous server
process require a new preview. Run one API worker for this MVP; multiple workers
would need a shared preview store. Saved calendars and Undo remain in SQLite.

Automated tests cover both operation constraints, movement/deferral priorities,
elapsed-time protection, time-zone conversion, read-only previews, exact commits,
protected conflicts, stale revisions (including edit/Undo cycles), expiration,
restart behavior, validation, solver failures, and Undo. Run:

```sh
mise run backend-test
mise run frontend-build
```

The frontend build checks TypeScript and bundles the app. Browser interaction
checks remain manual when no connected browser is available; use the checklist
in [frontend/README.md](../frontend/README.md).
