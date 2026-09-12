# Three-day presentation demo

The demo covers September 11, 12, and 13, 2026. Use the day tabs to navigate.
Each day remains an independent 8 AM–midnight, 30-minute-slot schedule with its
own Undo snapshot. Tasks do not automatically move between days or span midnight.

## Presentation clock

The first frontend visit starts the shared clock at **September 11, 8 AM**.
Click **Edit time** beside the paused clock, choose **Current day** and **Current time**,
then click **Set demo time** to change
it. The clock stays paused until changed, and may move forward or backward within
the three dates. All displayed demo times are New York wall time, regardless of
the browser machine's time zone. The calendar tab and simulated current date are
independent; **Demo today** returns to the simulated current date.

The clock lives in SQLite and survives refreshes and backend restarts. Other tabs
pick up clock changes within three seconds. It is shared by all users of this
demo database. Changing it never changes saved tasks or deletes Undo snapshots.
It does invalidate all pending move/extend previews and new-item options, even
if the new time is in the same half-hour interval or you later restore the old
time. The frontend closes drafts/previews and reloads the displayed day when the
clock revision changes.

## Suggested walkthrough

1. Set the clock to September 11 at 8 AM. Select the Sep 11 tab.
2. On an empty day, click **Load sample day**. This only populates that day;
   repeat on the other tabs as desired. Sample IDs are distinct for each date.
   Existing saved days are never overwritten by sample loading.
3. Drag a flexible task onto another task, wait for the proposal, and drop.
   Show the changes and use Undo.
4. Select **Running late?**, preview an extension, Apply, and Undo.
5. Set the clock to September 11 at 10:15 AM. New placements must start at 10:30 AM
   or later. A new fixed event cannot start in elapsed time. Already-started
   non-target tasks remain protected when adding or rescheduling.
6. Open Sep 12: future-day placements can use the entire day starting at 8 AM.
7. Set the clock to September 12 at 10:15 AM. Sep 11 is now a historical view;
   to add or reschedule there, move the demo clock back. Explicit edits/deletions
   and Undo can still change historical records, but never backfill elapsed gaps
   with other work. Sample loading remains available for an empty historical day.
8. Refresh: confirm the clock is unchanged and all three calendars are preserved.
9. Change one day's schedule, visit another day, then return and Undo. Other days
   must remain unchanged.

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

Run the existing build and test commands in [README.md](../README.md). Automated
tests cover date isolation, clock persistence, time boundaries, stale proposals,
historical Undo, and distinct sample IDs. Browser verification is still needed
when a connected browser is available.
