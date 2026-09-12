# Tetris frontend — Phase 1

See the [root README](../README.md#build-run-and-test-commands) for setup,
development, build, test, and preview commands. That is the shared command
reference for the project.

## Implemented

- Scrollable 8 AM–midnight calendar with all three dates on one shared time axis.
- Fixed events with start/end times; flexible tasks with duration, Available from,
  and Deadline date/time.
- Add, edit/reschedule, and delete through forms, the task list, and item details.
- September 11–13 side-by-side columns and a contextual task list.
- A paused presentation clock and matching current-time marker, shared with the backend.
- FastAPI-backed add, edit, delete, pin, and load operations.
- Live drag-to-time and cross-day previews, plus a Move task dialog for keyboard/touch use.
- Current/Proposed calendar toggles before applying a new-item proposal,
  drag-and-drop, or item edit.
- Running-late extensions from 30 minutes to two hours, with preview before Apply.
- Up to two real CP-SAT schedule options when adding a fixed event or flexible
  task; selecting an option previews the complete calendar without saving it.
- Dated moved/deferred explanations and shared three-day Undo for optimizer
  commits, edits, deletion, and pin changes; the snapshot survives refreshes.
- Cross-day Move task selection and day tabs inside new-item option previews.
- A confirmed **↻ Debug reset** action that loads a repeatable three-day stress scenario.
- Atomic additions: protected conflicts or placement failures show an error
  without changing the saved day.

The app starts on the demo clock's current day. An empty day offers a
button to load sample data. Calendar changes persist in SQLite across refreshes.
All three date columns remain visible. Use a column header to choose which day
task actions refer to without changing the clock. The **Set demo time** control
changes scheduling time in New York. See [the demo guide](../doc/demo.md) for
presentation steps.
The debug reset replaces every task on all three dates and clears Undo, while
preserving the current demo time.
The left control rail contains Calendar/Tasks navigation, primary actions,
presentation controls, feedback, proposals, and Undo history.
It scrolls independently. There is no right sidebar or top metadata bar, allowing
the calendar timeline to use the full viewport height.

## Source map

- `src/types.ts`: shared item types. Slot 0 starts at 8 AM; boundary 32 is
  midnight. Deadlines are inclusive of finishing at that boundary. Pinning is
  a property of either kind of item.
- `src/api.ts`: typed requests to the calendar API.
- `src/App.tsx`: calendar/list views and state updates.
- `src/ItemForm.tsx` and `src/Dialog.tsx`: creation and accessible modal controls.
- `src/RunningLateDialog.tsx`: move/extend selection, proposals, and Apply.
- `src/useOptimizerPreview.ts`: debounced preview requests and stale-response protection.
- `src/ProposedChanges.tsx`: proposed placements and explanations.
- `src/ScheduleProposalPanel.tsx`: compares, previews, and accepts new-item options.

The Python CP-SAT scheduler is authoritative. It minimizes deferral, then a
weighted score for moved-task count, total displacement, largest individual
displacement, and calendar days crossed. Dragging and running late use different
default weights; see [optimizer.md](../doc/optimizer.md). It considers all three
dates while keeping each task entirely within one day. Existing tasks keep
same-day deadlines until the user explicitly extends their deadline date.

## Manual demo check

1. Add a flexible task with a 30-minute duration and a 5 PM deadline. Preview
   its solver-selected placements; each must use an available future half-hour
   while existing started items stay put.
2. Use Edit from the Tasks view, change its duration or deadline, and select
   Preview update. Toggle Current/Proposed, apply it, and confirm the same item
   updates without creating a duplicate.
3. Add a fixed event with one start time and confirm the mini-calendar review
   shows the optimized day while the saved day remains unchanged. Toggle between
   Current schedule and Proposed addition. Add an optional alternative start,
   switch between both real schedule options, then apply one and confirm Undo
   restores the day without the new event.
4. Add a flexible task with enough room before its deadline for at least two
   placements. Confirm both options use different solver-selected start times,
   then apply one and Undo it.
5. Try adding a fixed event over the seeded pinned Gym task. The form should
   report the protected conflict and leave the day unchanged.
6. Delete an item directly from Tasks, then delete one from its detail dialog.
   Check the free-time total after each deletion.
7. Scroll to Gym at 6 PM, Read at 8 PM, and the midnight boundary. The timeline
   and time labels should scroll together. Also check a narrow phone viewport.
8. Choose **Running late?**, select a current or future item, and add 30 minutes.
   Inspect proposed moves/deferrals; Cancel must leave the calendar unchanged.
   Reopen, preview, and Apply. Confirm the update panel matches the proposal.
9. Refresh the page and confirm **Undo changes** is still available. Use it and
   verify the exact prior durations and placements return.
10. Create two future flexible tasks, then drag one onto the other's time. Pause
    until a proposal appears. Verify cards preview new placements, then drop and
    toggle Current/Proposed before applying. Undo must restore both tasks.
    Repeat by dragging one task into another date column; the preview should
    update all three columns and the drop should preserve its duration.
11. Drag a past unpinned flexible task into a future slot and verify a proposal
    appears. Then drag over a fixed/pinned item or elapsed target time and verify
    the conflict is shown. Releasing an invalid drop must not save; Escape or
    release outside the grid should cancel.
12. Rapidly change drag targets and running-late selections; an old response
    must never replace the current proposal. Drop before a valid preview is
    ready and confirm nothing is saved. Hover near the grid edge to scroll.
13. Use **Move task** in an item's details with only the keyboard and in a narrow
    viewport. Confirm preview, Apply, Cancel, and deferred-task selection work.
14. Keep a preview open, edit any of the three days in another tab, then Apply. The stale
    proposal must be rejected. Repeat after a half-hour time boundary passes.
15. Follow the cross-day walkthrough in [demo.md](../doc/demo.md). Confirm dates
    in the change list, the destination column, and Undo from another selected day.

Backend scheduling/API checks, frontend type-checking, and the production build
pass. Browser interaction and visual checks still need to be run when a browser
is available.
