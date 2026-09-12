# Three-day presentation demo

The demo covers September 11, 12, and 13, 2026. The calendar displays all three
days side by side on one shared time axis. A compact scrolling left rail holds
the day context, Add and Running late actions, demo clock, reset, feedback,
proposals, and Undo details. There is no right sidebar or top metadata bar, so
the calendar uses the full viewport height.
The optimizer considers all three 8 AM–midnight, 30-minute-slot calendars together.
Flexible tasks can move between eligible dates, with a penalty per day crossed.
Each task remains one continuous interval within one day. A shared one-level
Undo snapshot restores all three calendars to before the latest accepted
optimizer adjustment, item edit, deletion, or pin change.

## Presentation clock

The first frontend visit starts the shared clock at **September 11, 8 AM**.
Click **Edit time** beside the paused clock, choose **Current day** and **Current time**,
then click **Set demo time** to change
it. The clock stays paused until changed, and may move forward or backward within
the three dates. All displayed demo times are New York wall time, regardless of
the browser machine's time zone. Click a calendar column heading to make it the
date used by Add and Running late without changing the simulated clock.

The clock lives in SQLite and survives refreshes and backend restarts. Other tabs
pick up clock changes within three seconds. It is shared by all users of this
demo database. Changing it never changes saved tasks or deletes Undo snapshots.
It does invalidate all pending move/extend/edit previews and new-item options, even
if the new time is in the same half-hour interval or you later restore the old
time. The frontend closes drafts/previews and reloads the displayed day when the
clock revision changes.

## Suggested walkthrough

1. Click **↻ Debug reset** and confirm. This replaces all three schedules and
   clears Undo; the presentation clock is preserved.
2. Set the clock to September 11 at 8 AM and select the Sep 11 column.
3. Choose **Running late?**, extend **Client review** by 60 minutes, and inspect
   the dated changes. At least one eligible Sep 11 task moves to a later date.
4. Open the destination day, then use Undo to restore the complete window.
5. Drag a flexible task onto another task, wait for the proposal, and drop.
   Toggle between Current schedule and Proposed update, then Apply. Show the
   saved changes and use Undo.
   Then drag an eligible flexible task horizontally into a later date column;
   the ghost target and collateral tasks update across all three days before drop.
6. Set the clock to September 11 at 10:15 AM. New placements must start at 10:30 AM
   or later. A new fixed event cannot start in elapsed time. Already-started
   non-target tasks remain protected when adding or rescheduling.
7. Select Sep 12: future-day placements can use the entire day starting at 8 AM.
8. Set the clock to September 12 at 10:15 AM. Sep 11 is now a historical view;
   to add or reschedule there, move the demo clock back. Explicit edits/deletions
   and Undo can still change historical records, but never backfill elapsed gaps
   with other work. Sample loading remains available for an empty historical day.
9. Refresh: confirm the clock is unchanged and all three calendars are preserved.
10. Apply a change, visit another day, and Undo there. All three days must match
   the saved window from before that adjustment.

The fixture includes dense and open periods, same-day and cross-day deadlines,
fixed events, three pinned tasks, and two intentionally deferred tasks. Sep 11
is fully occupied so delay and resizing cases create meaningful collateral moves.
Sep 12 and Sep 13 provide gaps for additions and drag tests while retaining fixed
blockers and final-day deadline pressure.

## Cross-day walkthrough

Use empty calendars and set the clock to September 11 at 8 AM.

1. Add a fixed event on Sep 11 from 8 AM to 10 PM, then a second fixed event
   from 10 PM to 11 PM.
2. Add a one-hour flexible task with Available from Sep 11 and Deadline date
   Sep 12 at 10 AM. Apply its Sep 11, 11 PM option.
3. Extend the 10 PM fixed event by 60 minutes. The flexible task now needs a
   continuous gap on Sep 12; the proposal lists both dates. Apply it.
4. Select Sep 12 to see the task, then Undo from that context. Both its original
   Sep 11 placement and the event's original duration must return.

New and existing tasks default to same-day deadlines. Extend Deadline date to
allow automatic cross-day movement. Available from prevents work being pulled
into an earlier day; fixed, pinned, and other already-started items stay put.
The Move task dialog also supports selecting an explicit destination day.

The default day-change weight is 24 per day crossed in both move and extension
profiles. API clients can override `penalties.dayChange`; the UI uses defaults.
Date-change cost is added to actual time displacement, including the overnight
gap. Avoiding deferral still takes priority over all movement penalties.

The ordinary add endpoint can save an unplaceable task as deferred. The newer
add-options UI requires the new item to fit and reports that no option is
available when it cannot. This existing distinction is unchanged by the demo.

## Clock API

`POST /api/demo/start` starts the demo idempotently, preserving an existing clock.
`GET /api/demo/clock` reads it. `PUT /api/demo/clock` changes it:

```json
{"now": "2026-09-12T10:15:00"}
```

`now` must be a local timestamp without an offset, within September 11–13, 2026.
An invalid timestamp, offset, or date returns `422`. Successful calls return:

```json
{
  "now": "2026-09-12T10:15:00",
  "revision": 2,
  "timeZone": "America/New_York",
  "startDate": "2026-09-11",
  "endDate": "2026-09-13"
}
```

Before the demo is started, a read returns the initial value with revision 0 and
existing API clients still use the real server clock. Starting or setting it
activates demo mode. Once active, the demo's New York wall time takes precedence
over request time zones. Optimizer/add requests outside the three dates are
rejected; the underlying storage still supports reading other dates.

Clock updates and commits use SQLite write transactions. Every preview stores
the clock revision read in the same transaction as its calendar data; commit
rejects a changed clock with `409`. Proposal lifetimes still use 120 seconds of
real elapsed time, so freezing or rewinding the demo clock does not extend them.

## Debug reset API

`POST /api/debug/reset?day=2026-09-11` replaces the complete three-day schedule
in one SQLite transaction. `day` controls which date is returned in top-level
`items`; the response's `days` array always contains the full fixture. The reset
clears Undo and invalidates pending optimizer previews through revision changes.
It does not change the presentation clock. Dates outside September 11–13 return
`409`.

Run the existing build and test commands in [README.md](../README.md). Automated
tests cover cross-day placement, indivisible tasks, day-change penalties, dated
deadlines, clock persistence, stale proposals, shared Undo, and distinct sample
IDs. Browser verification is still needed
when a connected browser is available.
