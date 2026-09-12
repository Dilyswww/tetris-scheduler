import { useEffect, useRef, useState } from "react";
import type { CSSProperties, DragEvent } from "react";
import type { CalendarItem, DaySchedule, ScheduleChange } from "./types.ts";
import { DAY_START_HOUR, SLOTS_PER_DAY } from "./types.ts";
import { formatDuration, formatSlot, localDateKey } from "./time.ts";
import { ApiError, calendarApi } from "./api.ts";
import { ItemForm } from "./ItemForm";
import { Dialog } from "./Dialog";
import { RunningLateDialog } from "./RunningLateDialog";
import { useOptimizerPreview } from "./useOptimizerPreview";
import { ProposedChanges } from "./ProposedChanges";

const SLOT_HEIGHT = 48;
const boundaries = Array.from({ length: SLOTS_PER_DAY + 1 }, (_, slot) => slot);

function CalendarCard({ item, onSelect, draggable = false, proposed = false, onDragStart, onDragEnd }: {
  item: CalendarItem; onSelect: () => void; draggable?: boolean; proposed?: boolean;
  onDragStart?: (event: DragEvent<HTMLButtonElement>) => void; onDragEnd?: () => void;
}) {
  if (item.startSlot === null) return null;
  return (
    <button type="button" draggable={draggable} onDragStart={onDragStart} onDragEnd={onDragEnd}
      className={`calendar-card ${item.kind} ${item.accent} ${item.isPinned ? "is-pinned" : ""} ${proposed ? "is-proposed" : ""}`}
      style={{ top: item.startSlot * SLOT_HEIGHT + 3, height: item.durationSlots * SLOT_HEIGHT - 6 }}
      onClick={onSelect} aria-label={`${item.title}, ${formatSlot(item.startSlot)} to ${formatSlot(item.startSlot + item.durationSlots)}, ${item.kind}${item.isPinned ? ", pinned" : ""}`}>
      <span className="card-heading"><strong>{item.title}</strong>{item.isPinned && <span className="pin">Pinned</span>}</span>
      <span className="card-time">{formatSlot(item.startSlot)} · {formatDuration(item.durationSlots)}</span>
      {item.durationSlots > 1 && <small>{item.kind === "flexible" ? `Due ${formatSlot(item.deadlineSlot)}` : item.note || "Fixed event"}</small>}
    </button>
  );
}

export function App() {
  const [day] = useState(() => new Date());
  const date = localDateKey(day);
  const dateLabel = day.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const weekday = day.toLocaleDateString("en-US", { weekday: "long" });
  const [items, setItems] = useState<CalendarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"calendar" | "tasks">("calendar");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<CalendarItem | null>(null);
  const [reportingLate, setReportingLate] = useState(false);
  const [movingId, setMovingId] = useState<string | null>(null);
  const [drag, setDrag] = useState<{ itemId: string; slot: number; offset: number } | null>(null);
  const [committing, setCommitting] = useState(false);
  const commitLock = useRef(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [changes, setChanges] = useState<ScheduleChange[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [solverStatus, setSolverStatus] = useState<DaySchedule["solverStatus"]>(null);
  const [undoing, setUndoing] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const calendarRef = useRef<HTMLDivElement>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const selected = items.find((item) => item.id === selectedId);
  const dragProposal = useOptimizerPreview(drag ? { type: "move", itemId: drag.itemId, targetStartSlot: drag.slot } : null, items);
  const previewItems = dragProposal.preview?.schedule.items ?? items;

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    calendarApi.getDay(date)
      .then((schedule) => { if (active) applySchedule(schedule); })
      .catch((error: unknown) => { if (active) setFeedback(messageFor(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [date]);

  const plannedSlots = items.filter((item) => item.startSlot !== null).reduce((sum, item) => sum + item.durationSlots, 0);
  const focusSlots = items.filter((item) => item.kind === "flexible" && item.startSlot !== null).reduce((sum, item) => sum + item.durationSlots, 0);
  const openSlots = SLOTS_PER_DAY - plannedSlots;
  const orderedItems = [...items].sort((a, b) => (a.startSlot ?? 32) - (b.startSlot ?? 32));
  const nowSlot = (now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60 - DAY_START_HOUR * 60) / 30;
  const showNow = localDateKey(now) === date && nowSlot >= 0 && nowSlot < SLOTS_PER_DAY;
  const nextItem = orderedItems.find((item) => item.startSlot !== null && item.startSlot >= nowSlot);

  function applySchedule(schedule: DaySchedule) {
    setItems(schedule.items);
    setChanges(schedule.changes);
    setCanUndo(schedule.canUndo);
    setSolverStatus(schedule.solverStatus);
    setDrag(null);
  }

  async function addItem(item: CalendarItem) {
    try {
      const result = await calendarApi.addItem(item);
      const placed = result.items.find((entry) => entry.id === item.id)!;
      const moved = items.filter((entry) => result.items.find((next) => next.id === entry.id)?.startSlot !== entry.startSlot);
      applySchedule(result);
      setFeedback(`Added ${placed.title}${placed.startSlot === null ? " to Needs attention because no valid gap is available" : ` at ${formatSlot(placed.startSlot)}`}.${moved.length ? ` Changed ${moved.map((entry) => `${entry.title} to ${placementLabel(result.items.find((next) => next.id === entry.id)!.startSlot)}`).join(", ")} to make room.` : ""}`);
      return null;
    } catch (error) {
      return messageFor(error);
    }
  }

  async function updateItem(item: CalendarItem) {
    try {
      const previous = items.find((entry) => entry.id === item.id)!;
      const result = await calendarApi.updateItem(item);
      const updated = result.items.find((entry) => entry.id === item.id)!;
      const moved = result.items.filter((entry) => {
        const old = items.find((candidate) => candidate.id === entry.id);
        return old && old.startSlot !== entry.startSlot;
      });
      applySchedule(result);
      setFeedback(`Updated ${previous.title}.${moved.length ? ` Rescheduled ${moved.map((entry) => `${entry.title} to ${placementLabel(entry.startSlot)}`).join(", ")}.` : ` Kept at ${placementLabel(updated.startSlot)}.`}`);
      return null;
    } catch (error) {
      return messageFor(error);
    }
  }

  function editItem(item: CalendarItem) {
    setSelectedId(null);
    setEditing(item);
  }

  async function togglePin(item: CalendarItem) {
    try {
      const result = await calendarApi.setPin(item.id, !item.isPinned);
      applySchedule(result);
      setFeedback(`${item.title} ${item.isPinned ? "unpinned" : `pinned at ${formatSlot(item.startSlot!)}`}.${item.kind === "fixed" ? " Fixed events always stay in place." : ""}`);
    } catch (error) {
      setFeedback(messageFor(error));
    }
  }

  async function removeItem(item: CalendarItem) {
    try {
      const result = await calendarApi.deleteItem(item.id);
      applySchedule(result);
      setSelectedId(null);
      setFeedback(`Deleted ${item.title}.`);
      addButtonRef.current?.focus();
    } catch (error) {
      setFeedback(messageFor(error));
    }
  }

  async function loadSample() {
    try {
      const result = await calendarApi.seedDay(date);
      applySchedule(result);
      setFeedback("Loaded a sample day. Your changes will now persist across refreshes.");
    } catch (error) {
      setFeedback(messageFor(error));
    }
  }

  async function commitAdjustment(previewToken: string) {
    if (commitLock.current) return "An adjustment is already being saved.";
    commitLock.current = true;
    setCommitting(true);
    try {
      const result = await calendarApi.commit(previewToken);
      applySchedule(result);
      const affected = Math.max(0, result.changes.length - 1);
      setFeedback(`Your day was adjusted${affected ? ` with ${affected} additional ${affected === 1 ? "change" : "changes"}` : " without moving anything else"}.`);
      return null;
    } catch (error) {
      return messageFor(error);
    } finally {
      commitLock.current = false;
      setCommitting(false);
    }
  }

  async function undoReschedule() {
    setUndoing(true);
    try {
      const result = await calendarApi.undo(date);
      applySchedule(result);
      setFeedback("Restored your day to the schedule from before the last adjustment.");
    } catch (error) {
      setFeedback(messageFor(error));
    } finally {
      setUndoing(false);
    }
  }

  function showCalendar() {
    setView("calendar");
    calendarRef.current?.scrollTo({ top: 0 });
  }

  function dragStart(event: DragEvent<HTMLButtonElement>, item: CalendarItem) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", item.id);
    const offset = Math.floor((event.clientY - event.currentTarget.getBoundingClientRect().top) / SLOT_HEIGHT);
    setDrag({ itemId: item.id, slot: item.startSlot!, offset });
  }

  function targetSlot(event: DragEvent<HTMLDivElement>) {
    return Math.max(0, Math.min(31, Math.floor((event.clientY - event.currentTarget.getBoundingClientRect().top) / SLOT_HEIGHT) - (drag?.offset ?? 0)));
  }

  function dragOver(event: DragEvent<HTMLDivElement>) {
    if (!drag) return;
    event.preventDefault();
    const slot = targetSlot(event);
    event.dataTransfer.dropEffect = dragProposal.preview && slot === drag.slot ? "move" : "none";
    if (slot !== drag.slot) setDrag({ ...drag, slot });
    const scroll = calendarRef.current;
    if (scroll) {
      const bounds = scroll.getBoundingClientRect();
      if (event.clientY < bounds.top + 48) scroll.scrollTop -= 18;
      else if (event.clientY > bounds.bottom - 48) scroll.scrollTop += 18;
    }
  }

  async function dropTask(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    const proposal = dragProposal.preview;
    const matches = drag && targetSlot(event) === drag.slot;
    setDrag(null);
    if (!matches || !proposal) {
      setFeedback(dragProposal.error || "Wait for a valid preview before dropping the task. Nothing was saved.");
      return;
    }
    const failure = await commitAdjustment(proposal.previewToken);
    if (failure) setFeedback(failure);
  }

  return (
    <><main aria-busy={committing} inert={committing}>
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">T</span><span>Tetris</span></div>
        <nav aria-label="Main navigation">
          <button className={`nav-item ${view === "calendar" ? "active" : ""}`} aria-current={view === "calendar" ? "page" : undefined} onClick={showCalendar}><span aria-hidden="true">▦</span> Today</button>
          <button className={`nav-item ${view === "tasks" ? "active" : ""}`} aria-current={view === "tasks" ? "page" : undefined} onClick={() => setView("tasks")}><span aria-hidden="true">☷</span> Tasks <span className="nav-count">{items.length}</span></button>
        </nav>
        <section className="sidebar-card">
          <p className="eyebrow">TODAY'S RHYTHM</p><strong>{formatDuration(focusSlots)}</strong><span>of focused work planned</span>
          <div className="progress"><i style={{ width: `${focusSlots / SLOTS_PER_DAY * 100}%` }} /></div>
        </section>
        <div className="sidebar-footer"><div className="avatar" aria-hidden="true">T</div><div><strong>Your daily plan</strong><span>8:00 AM – midnight</span></div></div>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">YOUR ADAPTIVE DAY</p><h1>{dateLabel}</h1></div>
          <div className="top-actions"><button className="today-button" onClick={showCalendar}>Today</button><button className="late-top-button" onClick={() => setReportingLate(true)} disabled={!items.some((item) => item.startSlot !== null)}>Running late?</button><button ref={addButtonRef} className="add-button" onClick={() => setAdding(true)}>+ Add task</button></div>
        </header>
        <div className="feedback" role="status" aria-live="polite">{feedback || "Drag a flexible task to preview a new time, or select an item for more actions."}</div>
        {drag && <section className="drag-proposal" aria-label="Drag preview" aria-live="polite">
          <strong>{dragProposal.loading ? `Checking ${formatSlot(drag.slot)}…` : dragProposal.error ? "This time is unavailable" : `Preview at ${formatSlot(drag.slot)} · drop to apply`}</strong>
          <span>{dragProposal.error || "Other flexible tasks can move earlier or later. Release outside the calendar or press Escape to cancel."}</span>
          {dragProposal.preview && <ProposedChanges changes={dragProposal.preview.schedule.changes} />}
        </section>}
        {(changes.length > 0 || canUndo) && <ChangePanel changes={changes} canUndo={canUndo} solverStatus={solverStatus} undoing={undoing} onUndo={undoReschedule} />}
        <div className="content">
          {view === "calendar" ? <section className="calendar-panel" aria-label="Day calendar" aria-busy={loading}>
            <div className="calendar-header"><span>Time</span><strong>{weekday} <span className="grid-caption">· 30-minute slots</span></strong></div>
            <div className="calendar-scroll" ref={calendarRef} tabIndex={0} role="region" aria-label="Calendar, 8 AM to midnight">
              <div className="calendar-body" style={{ "--slot-height": `${SLOT_HEIGHT}px` } as CSSProperties}>
                <div className="time-column">{boundaries.map((slot) => <span key={slot}>{slot % 2 === 0 ? formatSlot(slot) : ""}</span>)}</div>
                <div className="grid" onDragOver={dragOver} onDrop={dropTask}>
                  {boundaries.slice(0, -1).map((slot) => <div className="grid-line" key={slot} />)}
                  {showNow && <div className="now-line" style={{ top: nowSlot * SLOT_HEIGHT }}><i /><span>{now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</span></div>}
                  {previewItems.map((item) => <CalendarCard key={item.id} item={item} onSelect={() => { if (!drag) setSelectedId(item.id); }}
                    draggable={item.kind === "flexible" && !item.isPinned && item.startSlot !== null && item.startSlot >= nowSlot}
                    proposed={!!dragProposal.preview && dragProposal.preview.schedule.changes.some((change) => change.itemId === item.id)}
                    onDragStart={(event) => dragStart(event, item)} onDragEnd={() => setDrag(null)} />)}
                  {drag && <div className={`drop-target ${dragProposal.error ? "invalid" : ""}`} style={{ top: drag.slot * SLOT_HEIGHT, height: (items.find((item) => item.id === drag.itemId)?.durationSlots ?? 1) * SLOT_HEIGHT }} />}
                  {!loading && !items.length && <div className="calendar-empty"><strong>Your day is clear.</strong><span>Add an item or load the sample schedule.</span><button className="secondary-button" onClick={loadSample}>Load sample day</button></div>}
                </div>
              </div>
            </div>
          </section> : <section className="task-list-panel" aria-labelledby="task-list-title">
            <div className="list-heading"><h2 id="task-list-title">Your tasks & events</h2><span>{items.length} planned</span></div>
            {orderedItems.map((item) => <div key={item.id} className="task-row">
              <button type="button" className="task-row-open" onClick={() => setSelectedId(item.id)} aria-label={`Open details for ${item.title}`}>
                <span className={`task-swatch ${item.accent}`} aria-hidden="true" />
                <span className="task-row-main"><strong>{item.title}</strong><span>{item.kind === "fixed" ? "Fixed event" : `Flexible task · due ${formatSlot(item.deadlineSlot)}`}{item.isPinned ? " · Pinned" : ""}</span></span>
                <span className={`task-row-time ${item.startSlot === null ? "deferred-text" : ""}`}>{placementLabel(item.startSlot)}<small>{item.startSlot === null ? "Deferred" : formatDuration(item.durationSlots)}</small></span>
              </button>
              <span className="task-row-actions">
                <button type="button" className="task-action-button" onClick={() => editItem(item)}>Edit</button>
                <button type="button" className="task-action-button task-delete-button" onClick={() => removeItem(item)}>Delete</button>
              </span>
            </div>)}
            {!loading && !items.length && <div className="empty-state"><p>Your day is a blank canvas.</p><button className="add-button" onClick={() => setAdding(true)}>Add your first task</button><button className="secondary-button" onClick={loadSample}>Load sample day</button></div>}
          </section>}
          <aside className="right-panel">
            <section className="notice-card"><div className="notice-icon" aria-hidden="true">✦</div><div><p className="eyebrow">{loading ? "SYNCING" : openSlots ? "ROOM TO BREATHE" : "FULL DAY"}</p><strong>{loading ? "Loading your day…" : `${formatDuration(openSlots)} available.`}</strong><span>{loading ? "Connecting to your saved calendar." : `${openSlots} open half-hour ${openSlots === 1 ? "slot" : "slots"}.`}</span></div></section>
            <section className="legend-card"><p className="eyebrow">SCHEDULE</p>
              <div><i className="legend-dot fixed-dot" /> Fixed events <span>Can't move</span></div><div><i className="legend-dot flex-dot" /> Flexible tasks <span>Can adapt</span></div><div><i className="legend-dot pin-dot" /> Pinned <span>Keep in place</span></div>
            </section>
            <section className="up-next"><div className="section-title"><p className="eyebrow">UP NEXT</p><button onClick={() => setView("tasks")}>View all</button></div>
              {nextItem ? <button className="next-card" onClick={() => setSelectedId(nextItem.id)}><span className="event-icon" aria-hidden="true">▣</span><span className="next-copy"><strong>{nextItem.title}</strong><span>{formatSlot(nextItem.startSlot!)} · {formatDuration(nextItem.durationSlots)}</span></span></button> : <p className="quiet-copy">No more items starting today.</p>}
              <button className="late-button" onClick={() => setReportingLate(true)} disabled={!items.some((item) => item.startSlot !== null)}>Running late?</button>
            </section>
          </aside>
        </div>
      </section>
      {adding && <ItemForm date={date} onSave={addItem} onClose={() => setAdding(false)} />}
      {editing && <ItemForm date={date} item={editing} onSave={updateItem} onClose={() => setEditing(null)} />}
      {reportingLate && <RunningLateDialog items={items} preferredId={nextItem?.id} onSubmit={commitAdjustment} onClose={() => setReportingLate(false)} />}
      {movingId && <RunningLateDialog items={items} preferredId={movingId} mode="move" onSubmit={commitAdjustment} onClose={() => setMovingId(null)} />}
      {selected && <Dialog title={selected.title} onClose={() => setSelectedId(null)}>
        <p className="detail-kind">{selected.kind === "fixed" ? "Fixed event" : "Flexible task"}{selected.isPinned ? " · Pinned" : ""}</p>
        <dl className="item-details"><div><dt>Time</dt><dd>{selected.startSlot === null ? "Deferred — needs attention" : `${formatSlot(selected.startSlot)} – ${formatSlot(selected.startSlot + selected.durationSlots)}`}</dd></div><div><dt>Duration</dt><dd>{formatDuration(selected.durationSlots)}</dd></div>
          {selected.kind === "flexible" && <div><dt>Finish by</dt><dd>{formatSlot(selected.deadlineSlot)}</dd></div>}
          {selected.note && <div><dt>Note</dt><dd>{selected.note}</dd></div>}
        </dl>
        <p className="form-hint">{selected.kind === "fixed" ? "Fixed events always stay at their chosen time." : selected.startSlot === null ? "No valid continuous gap remains before this task's deadline. Edit it or free calendar space so the optimizer can schedule it later." : selected.isPinned ? "Pinned tasks keep this exact time when other items are added." : "Flexible tasks can move when a fixed event needs this time."}</p>
        <div className="dialog-actions"><button className="delete-button" onClick={() => removeItem(selected)}>Delete item</button><button className="secondary-button" onClick={() => editItem(selected)}>Edit item</button><button className="secondary-button" aria-pressed={selected.isPinned} disabled={selected.startSlot === null} onClick={() => togglePin(selected)}>{selected.isPinned ? "Unpin item" : "Pin item"}</button>
          {selected.kind === "flexible" && !selected.isPinned && <button className="secondary-button" onClick={() => { setMovingId(selected.id); setSelectedId(null); }}>Move task</button>}
        </div>
      </Dialog>}
    </main>{committing && <div className="saving-overlay" role="status">Saving your adjustment…</div>}</>
  );
}

function messageFor(error: unknown) {
  return error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function ChangePanel({ changes, canUndo, solverStatus, undoing, onUndo }: { changes: ScheduleChange[]; canUndo: boolean; solverStatus: DaySchedule["solverStatus"]; undoing: boolean; onUndo: () => void }) {
  return <section className="change-panel" aria-labelledby="change-heading">
    <div className="change-panel-heading"><div><p className="eyebrow">SCHEDULE UPDATE{solverStatus ? ` · ${solverStatus.toUpperCase()}` : ""}</p><h2 id="change-heading">{changes.length ? `${changes.length} ${changes.length === 1 ? "change" : "changes"} to your day` : "Your last adjustment can be undone"}</h2></div>{canUndo && <button className="undo-button" onClick={onUndo} disabled={undoing}>{undoing ? "Restoring…" : "↶ Undo changes"}</button>}</div>
    {changes.length > 0 && <div className="change-list">{changes.map((change) => <article className={`change-item ${change.changeType}`} key={`${change.itemId}-${change.changeType}`}>
      <span className="change-badge">{change.changeType}</span><div><strong>{change.title}</strong><span>{changeSummary(change)}</span><small>{change.reason}</small></div>
    </article>)}</div>}
  </section>;
}

function changeSummary(change: ScheduleChange) {
  if (change.changeType === "extended") return `${formatDuration(change.fromDurationSlots!)} → ${formatDuration(change.toDurationSlots!)}`;
  if (change.fromStartSlot !== change.toStartSlot) return `${placementLabel(change.fromStartSlot)} → ${placementLabel(change.toStartSlot)}`;
  if (change.fromDurationSlots !== change.toDurationSlots) return `${formatDuration(change.fromDurationSlots!)} → ${formatDuration(change.toDurationSlots!)}`;
  return "Previous placement restored";
}

function placementLabel(slot: number | null) {
  return slot === null ? "Needs attention" : formatSlot(slot);
}
