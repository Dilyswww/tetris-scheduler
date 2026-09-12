# Optimizer: drag a task or extend an item

The optimizer considers **September 11–13, 2026 together**. Each day has 32
indivisible 30-minute slots from 8 AM to midnight. Slot 0 means 8 AM; end boundary
32 means midnight. Flexible tasks can change dates within their availability and
deadline bounds. Each task stays one continuous block entirely within one day:
no splitting, overnight spans, or combining fragments across dates.
The [demo clock](demo.md) controls the simulated present. There is one shared
Undo snapshot for the three-day window. API dates outside the demo window retain
single-day planning before demo mode starts.

Intervals are half-open: `[startSlot, startSlot + durationSlots)`. Tasks cannot
split or span midnight. OR-Tools CP-SAT owns placement decisions.

## Two operations, one solver

| Rule | Move / drag | Extend / running late |
| --- | --- | --- |
| User intent | Reserve a particular start time | Reserve more time at the existing start |
| Selected item | Unpinned flexible task, including a deferred task through Move task | Any scheduled item, including fixed or pinned |
| Required placement | Exactly `targetDate` and `targetStartSlot` | Original start |
| Required duration | Original duration | Original duration plus 1–4 slots (30–120 minutes) |
| Can the selected item defer? | No | No |
| Can other flexible tasks move earlier? | Yes, into time that has not elapsed, including the vacated slot | Yes, if that time has not elapsed |
| Protected work | Fixed, pinned, and already-started items other than the explicitly moved target | Fixed, pinned, and already-started items other than the explicitly extended target |

These actions have different feasibility constraints, rather than competing
versions of the same placement preference. A drag's chosen start is mandatory;
a penalty must never let the solver ignore the drop. An extension changes how
much time is available while preserving its start.

Both use a weighted score for **collateral changes**. Movement count no longer
has strict priority over movement distance. First minimize deferred tasks, then
minimize this score:

```text
movementScore = movedTask × movedTaskCount
              + displacementSlot × totalDisplacementSlots
              + largestDisplacementSlot × largestIndividualDisplacementSlots
              + dayChange × totalAbsoluteDayDistance
```

Displacement is absolute wall-time start distance, in 30-minute slots, including
the overnight gap: `abs(48 × dateDifference + newStartSlot − oldStartSlot)`.
Moving from 11 PM to the next day's 8 AM is 18 slots of displacement. The separate
day-change term charges per calendar day crossed: moving two days costs twice
as much as moving one. It applies to flexible tasks, including newly scheduled
or previously deferred tasks relative to their assigned date. The largest
individual displacement is zero if no previously scheduled task moves. The
default weights differ by operation:

| Weight | Move / drag | Extend / running late |
| --- | ---: | ---: |
| `movedTask` | 1 | 8 |
| `displacementSlot` | 2 | 2 |
| `largestDisplacementSlot` | 4 | 0 |
| `dayChange` | 24 | 24 |

Dragging favors small individual shifts; extending places more emphasis on
leaving other tasks untouched. These are tradeoffs, not guarantees of a minimum
move count. Ordinary window-wide placement and adding items use the move defaults.
For equal scores, prefer earlier placements; deferral tie costs prefer keeping
tasks with earlier deadlines and older positions in the window's item list.

### Regression: reorder 30 / 90 / 60 minutes

Originally A occupies minutes 0–30, B 30–120, and C 120–180. Drag A to 150–180:

- Keeping B unchanged and moving C to 180–240 costs `1×1 + 2×2 + 4×2 = 13`.
- Moving B to 0–90 and C to 90–150 costs `1×2 + 2×2 + 4×1 = 10`.

The compact B → C → A schedule wins, even though two other tasks move. The
requested move of A contributes nothing to these scores. There is no special
block boundary penalty: compactness is a consequence of smaller individual moves
in this example, not a general guarantee.

The requested move itself is excluded from collateral movement cost by locking
the target at its requested placement before optimization. Deferred tasks count
at the highest priority; they have no displacement. Newly placed tasks have no previous start
and therefore no moved-task or displacement penalty, but do pay day-change cost. Task priority, forward-only shifting, order
preservation, and schedule compression are not separate objectives in this MVP.

Example before 8 AM: A occupies slots 0–2 and B occupies 2–4. Drag A to slot 2:
B can move into the vacated 0–2 gap. Extend A by two slots instead: A occupies
0–4, so B must go elsewhere, such as 4–6. Both the required placements and the
default penalty weights differ between these operations.

## Task date bounds

Flexible tasks and drafts add `earliestDate` and `deadlineDate` (YYYY-MM-DD).
Omitting either defaults it to the task's `date`, preserving existing same-day
behavior. Set a later deadline date to allow automatic movement to another day.
`date` is the current assigned day, and must be between these date bounds.
The optimizer changes `date` when placing work elsewhere; it preserves the bounds.
When an unpinned flexible task is edited, its old date/start is a placement
preference rather than a hard constraint. Increasing its duration may temporarily
make that old interval exceed midnight; the request is still passed to CP-SAT,
which must move or defer the complete task before anything can be saved. Pinned
tasks retain strict placement validation. Running late remains different: it
represents work already in progress, so the selected item's start and date stay
fixed while other eligible tasks may move across days.

`deadlineSlot` applies only on `deadlineDate`. On earlier eligible days a task
may finish at midnight. The search never goes beyond September 13, even if an
API client supplies a later deadline. `durationSlots` remains 1–32. Pinned tasks
keep both their date and start. Deferred tasks keep their assigned date and have
`startSlot: null`.

## Time and protection rules

Requests supply an IANA `timeZone`, such as `America/New_York`. Before demo mode
starts, the server uses its real clock. The frontend starts a persistent paused
demo clock and exposes controls to change it. In demo mode, all scheduling uses
that shared New York wall time, including additions, edits, deletions, pinning,
move/extend/edit previews, and new-item proposals. See [demo.md](demo.md) for its API.

- For today, `earliestStartSlot` is the current local time rounded up to the
  next slot boundary, clamped to 0–32. At 10:15 AM this is slot 5, or 10:30 AM.
- For future days, it is 0. Past days have cutoff 32 and receive no automatic placements.
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
In demo mode, edit previews and direct edit/delete/pin operations preserve
started entries and do not backfill elapsed time with other tasks. The solver uses the real clock before demo mode starts. Undo
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
tasks that cannot fit anywhere in their remaining eligible window are saved as deferred.

### Preview: `POST /api/optimizer/preview`

Drag / choose a time:

```json
{
  "operation": {
    "type": "move",
    "itemId": "write-report",
    "targetStartSlot": 12,
    "targetDate": "2026-09-12"
  },
  "timeZone": "America/New_York",
  "penalties": {
    "movedTask": 1,
    "displacementSlot": 2,
    "largestDisplacementSlot": 4,
    "dayChange": 24
  }
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

Edit an existing item without saving it:

```json
{
  "operation": {
    "type": "edit",
    "item": {
      "id": "write-report",
      "title": "Finish report draft",
      "date": "2026-09-12",
      "kind": "flexible",
      "startSlot": 12,
      "durationSlots": 4,
      "deadlineSlot": 24,
      "earliestDate": "2026-09-12",
      "deadlineDate": "2026-09-13",
      "isPinned": false,
      "accent": "purple",
      "note": ""
    }
  },
  "timeZone": "America/New_York"
}
```

| Field | Contract |
| --- | --- |
| `operation.type` | Discriminator: `move`, `extend`, or `edit` |
| `operation.itemId` | Existing item ID for move/extend; determines the source day and optimization window |
| `operation.item` | Complete replacement `CalendarItem`, required only for edit; its ID determines the source item |
| `targetStartSlot` | Required only for move; integer 0–31; full duration must fit by the deadline |
| `targetDate` | Optional for move, defaults to the source date; must be within the window and task's date bounds |
| `additionalSlots` | Required only for extend; integer 1–4 |
| `timeZone` | Required IANA time-zone identifier |
| `penalties` | Optional object overriding the operation's default weights; omitted fields keep their operation-specific defaults |

Each penalty is an integer from 0 to 1000; zero disables that movement term.
Negative, fractional, Boolean, and unknown fields are rejected. The response
echoes the complete resolved weights. Weights do not relax fixed/pinned/started
placements, deadlines, overlap restrictions, or the priority of avoiding deferral.
Clients can tune them through the API; the UI currently uses the defaults.

Successful response, using TypeScript notation to show the exact shape:

```ts
type SchedulePreview = {
  previewToken: string;
  expiresInSeconds: 120;
  operation:
    | { type: "move"; itemId: string; targetStartSlot: number; targetDate?: string | null }
    | { type: "extend"; itemId: string; additionalSlots: number }
    | { type: "edit"; item: CalendarItem };
  earliestStartSlot: number; // 0–32, for the target day
  penalties: {
    movedTask: number;
    displacementSlot: number;
    largestDisplacementSlot: number;
    dayChange: number;
  };
  schedule: DaySchedule;
};

type DaySchedule = {
  date: string; // YYYY-MM-DD
  items: CalendarItem[]; // Source/requested day, including deferred items
  days: { date: string; items: CalendarItem[] }[]; // All three complete plans
  changes: ScheduleChange[];
  canUndo: boolean;
  solverStatus: "optimal" | "feasible" | null;
};

type ScheduleChange = {
  itemId: string;
  title: string;
  changeType: "added" | "extended" | "moved" | "deferred" | "scheduled" | "restored";
  fromDate: string | null;
  toDate: string | null;
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
uses `moved`, including when it previously had no placement. An edit target uses
`edited`; collateral placement changes remain `moved`, `scheduled`, or `deferred`.

Preview writes **nothing to SQLite**. It neither creates nor replaces Undo.
The nested `canUndo` describes the currently saved window's existing snapshot;
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
3. Confirm every day's revision still matches, including previously empty days.
4. Confirm the demo clock revision is unchanged, then recompute the time boundary
   for every day using the effective clock. If any changed, require a fresh preview.
5. Store all three days as one shared Undo snapshot, accessible from any selected day.
6. Delete the window's source rows before inserting destination rows, so IDs can
   move or swap dates safely. Save the exact proposal, increment every day's
   revision, and commit atomically.
7. Consume the token.

Any successful add, edit, delete, pin, seed, optimizer commit, or Undo increments
the revision. Thus a preview becomes stale even if later edits or Undo restore
identical item values. Reusing a committed token cannot apply the change twice.
Failed operations do not modify any day or its snapshot.

### Multiple new-item options

`POST /api/optimizer/proposals` accepts an unsaved fixed-event or flexible-task
draft and an IANA time zone. Fixed events include one to four distinct candidate
start slots; each is locked in turn and solved by CP-SAT. For flexible tasks,
CP-SAT first finds the best required placement, then solves again while excluding
that exact `(date, startSlot)` to produce the best distinct alternative. If only one placement is
feasible, one option is returned. All solves use the same window revisions and
per-day time boundaries. Infeasible options are omitted; a `409` is returned only when no
placement is feasible. The response contains a temporary `proposalSetId` and the
real schedule, structured changes, and disruption metrics for each option.
Each alternative includes `date`, `startSlot`, a full `schedule.days` array,
and `metrics.dayChangeCount` (existing scheduled tasks changing dates).
Alternatives are ranked by the solver's complete weighted objective, including
day-change cost, and the first is labeled Recommended.
The frontend can toggle the full calendar between Current schedule and Proposed
addition, then switch among the proposed alternatives. Generating, toggling, or
switching options never writes to SQLite.

`POST /api/optimizer/proposals/{proposalSetId}/accept` accepts an
`alternativeId`. It validates the set's 120-second lifetime, all day revisions, and per-day time
boundaries, stores the current schedule as the Undo snapshot, and persists the
exact selected schedule without solving again. Accepting one alternative
invalidates the entire set, so another option cannot be applied afterward.
The client never submits a replacement schedule.

### Undo: `POST /api/day/{date}/undo`

Restores all three days' exact saved item payloads, returns dated `restored`
change records, clears the shared one-level snapshot, and increments all window
revisions. The route's date only chooses the response's top-level `items`; Undo
from any selected day restores the same most recent window adjustment. Undo persists across app
restarts. A successful optimizer commit, accepted new-item proposal, edit,
delete, or pin/unpin replaces the previous snapshot with the state immediately
before that action. Failed requests preserve the existing snapshot. Seed/debug
reset operations and the low-level direct-add route clear it.

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
The main calendar shows all three dates side by side. Horizontal position selects
`targetDate`; vertical position snaps to a half-hour `targetStartSlot`, accounting
for where the card was grabbed. After 150 ms at a target, the client requests a
preview. The source card stays under the pointer, a ghost marks the destination,
and collateral tasks update across all three columns without changing saved
state. Invalid targets show an error. Dropping a ready proposal opens a review
that toggles the calendar between Current schedule and Proposed update. Apply
commits the exact preview; Cancel, releasing outside the calendar, or Escape
leaves the saved schedule unchanged. If no valid proposal is ready, no review
opens. Edge hovering scrolls the shared timeline.

Calendar controls and schedule metadata live in an independently scrolling left
rail. Drag feedback, proposed changes, new-item alternatives, saved-change status,
and Undo stay in that rail instead of reducing the calendar timeline's height.

**Move task:** The item's detail dialog also offers a time selector with the
same preview and Apply flow, for keyboard and touch use and deferred tasks.
Its day selector supports explicit moves between eligible dates. Dragging on the
main calendar selects a time on the displayed day; collateral tasks can still
move to other days. New/edit task forms expose Available from and Deadline date.
Submitting an edit opens the same Current/Proposed review used after a drop;
the edit reaches SQLite only after Apply. New-item option mini-calendars have day
tabs, and all change lists show dates.

**Running late:** Choose an item and 30–120 extra minutes. The dialog previews
moved and deferred items automatically. Apply commits that proposal; Cancel
leaves all days untouched.

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
    required_ids: frozenset[str] = frozenset(),
    forbidden_starts: Mapping[str, frozenset[int]] | None = None,
    forbidden_placements: Mapping[str, frozenset[tuple[date, int]]] | None = None,
    earliest_start_slot: int = 0,
    days: Sequence[date] | None = None,
    earliest_starts: Mapping[date, int] | None = None,
    penalties: PenaltyWeights | None = None,
    time_limit_seconds: float = 0.5,
) -> SolverResult
```

This function copies its inputs. `SolverResult` contains `items`, `status`
(`optimal` or `feasible`), and the integer `objective_value`.
The repository translates the operation into an adjusted target, a lock set,
and per-day time boundaries; builds dated explanations against the original window; and owns
preview/commit/Undo. The solver performs no storage or HTTP work.

For each valid date/start pair the solver creates a Boolean `place[item, day, start]`.
Every unprotected flexible task also gets `deferred[item]`. Exactly one
placement or deferral is selected per item, and at most one selected interval
covers any `(day, slot)`. Each candidate's full duration must fit inside that day. Fixed, pinned, and explicitly locked items have only their
required date/start and cannot defer. All scheduled tasks finish by their deadline.

One integer objective encodes deferral count, the weighted movement score, and
final tie costs. An `add_max_equality` constraint computes the largest selected
individual displacement; deferred tasks contribute zero. The movement score is
scaled above the maximum possible total tie cost. The deferral weight is then
computed above the maximum possible movement score plus tie cost, including the
supplied penalty weights. Thus one fewer deferred task still dominates movement,
but one fewer moved task does not automatically beat smaller distances. Fixed
placements contribute only constant costs.

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
restart behavior, validation, solver failures, and Undo. Cross-day tests also
cover dated deadlines, fragmented gaps, day-change weight tradeoffs, future-day
staleness, window boundaries, restart-persistent Undo, and transaction rollback
after a destination write fails. Run:

```sh
mise run backend-test
mise run frontend-build
```

The frontend build checks TypeScript and bundles the app. Browser interaction
checks remain manual when no connected browser is available; use the checklist
in [frontend/README.md](../frontend/README.md).
