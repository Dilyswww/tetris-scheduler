import { useEffect, useRef, useState } from "react";
import type { CSSProperties, DragEvent, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import type { CalendarItem, DaySchedule, ProposalItemDraft, ProposalSet, ScheduleChange, SchedulePreview } from "./types.ts";
import { DAY_START_HOUR, DEMO_DATES, SLOTS_PER_DAY, scheduleItems } from "./types.ts";
import { earliestStartSlot, formatDate, formatDuration, formatSlot, localDateKey } from "./time.ts";
import { ApiError, calendarApi } from "./api.ts";
import { ItemForm } from "./ItemForm";
import { Dialog } from "./Dialog";
import { RunningLateDialog } from "./RunningLateDialog";
import { useOptimizerPreview } from "./useOptimizerPreview";
import { ProposedChanges } from "./ProposedChanges";
import { ScheduleProposalPanel } from "./ScheduleProposalPanel";
import { DemoClockControls, DemoClockProvider, useDemoClock } from "./DemoClock";

const SLOT_HEIGHT = 48;
const SIDEBAR_MIN_WIDTH = 240;
const SIDEBAR_MAX_WIDTH = 440;
const SIDEBAR_DEFAULT_WIDTH = 284;
const SIDEBAR_WIDTH_KEY = "tetris-sidebar-width";
const boundaries = Array.from({ length: SLOTS_PER_DAY + 1 }, (_, slot) => slot);

function clampSidebarWidth(width: number) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));
}

function storedSidebarWidth() {
  const saved = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
  return Number.isFinite(saved) && saved > 0 ? clampSidebarWidth(saved) : SIDEBAR_DEFAULT_WIDTH;
}

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
      {item.durationSlots > 1 && <small>{item.kind === "flexible" ? `Due ${formatDate(item.deadlineDate ?? item.date)} ${formatSlot(item.deadlineSlot)}` : item.note || "Fixed event"}</small>}
    </button>
  );
}

export function App() {
  return <DemoClockProvider><DemoCalendar /></DemoClockProvider>;
}

function DemoCalendar() {
  const { clock } = useDemoClock();
  const [date, setDate] = useState(clock.now.slice(0, 10));
  // A clock revision remounts pending previews; choosing a day only changes
  // the context for task actions because the calendar always shows all days.
  return <DayWorkspace key={clock.revision} date={date} onSelectDate={setDate} />;
}

function DayWorkspace({ date, onSelectDate }: { date: string; onSelectDate: (date: string) => void }) {
  const { now } = useDemoClock();
  const [itemsByDate, setItemsByDate] = useState<Record<string, CalendarItem[]>>(
    Object.fromEntries(DEMO_DATES.map((value) => [value, []])),
  );
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"calendar" | "tasks">("calendar");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<CalendarItem | null>(null);
  const [reportingLate, setReportingLate] = useState(false);
  const [movingId, setMovingId] = useState<string | null>(null);
  const [drag, setDrag] = useState<{ itemId: string; date: string; slot: number; offset: number } | null>(null);
  const [proposalSet, setProposalSet] = useState<ProposalSet | null>(null);
  const [selectedAlternativeId, setSelectedAlternativeId] = useState<string | null>(null);
  const [showNewItemProposal, setShowNewItemProposal] = useState(true);
  const [pendingUpdate, setPendingUpdate] = useState<{ preview: SchedulePreview; label: string } | null>(null);
  const [showProposedUpdate, setShowProposedUpdate] = useState(true);
  const [committing, setCommitting] = useState(false);
  const commitLock = useRef(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [changes, setChanges] = useState<ScheduleChange[]>([]);
  const [highlightedItemIds, setHighlightedItemIds] = useState<string[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [solverStatus, setSolverStatus] = useState<DaySchedule["solverStatus"]>(null);
  const [undoing, setUndoing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(storedSidebarWidth);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const sidebarWidthRef = useRef(sidebarWidth);
  const resizingSidebarRef = useRef(false);
  const calendarRef = useRef<HTMLDivElement>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const items = itemsByDate[date] ?? [];
  const allItems = DEMO_DATES.flatMap((value) => itemsByDate[value] ?? []);
  const selected = allItems.find((item) => item.id === selectedId);
  const dragProposal = useOptimizerPreview(drag ? { type: "move", itemId: drag.itemId, targetStartSlot: drag.slot, targetDate: drag.date } : null, itemsByDate);
  const selectedAlternative = proposalSet?.alternatives.find((option) => option.id === selectedAlternativeId) ?? proposalSet?.alternatives[0];
  const reviewedSchedule = pendingUpdate && showProposedUpdate ? pendingUpdate.preview.schedule : undefined;
  const newItemSchedule = showNewItemProposal ? selectedAlternative?.schedule : undefined;
  const activeSchedule = dragProposal.preview?.schedule ?? newItemSchedule ?? reviewedSchedule;
  const activePreviewChanges = dragProposal.preview?.schedule.changes ?? newItemSchedule?.changes ?? reviewedSchedule?.changes ?? [];
  const outlinedItemIds = new Set(activePreviewChanges.length
    ? activePreviewChanges.map((change) => change.itemId)
    : highlightedItemIds);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all(DEMO_DATES.map((value) => calendarApi.getDay(value)))
      .then((schedules) => {
        if (!active) return;
        setItemsByDate(Object.fromEntries(schedules.map((schedule) => [schedule.date, schedule.items])));
        setCanUndo(schedules.some((schedule) => schedule.canUndo));
        setChanges([]);
        setHighlightedItemIds([]);
        setSolverStatus(null);
      })
      .catch((error: unknown) => { if (active) setFeedback(messageFor(error)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!drag) return;
    const cancelDrag = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrag(null);
    };
    window.addEventListener("keydown", cancelDrag);
    return () => window.removeEventListener("keydown", cancelDrag);
  }, [drag]);

  const cutoff = earliestStartSlot(date, now);
  const orderedItems = [...items].sort((a, b) => (a.startSlot ?? 32) - (b.startSlot ?? 32));
  const today = localDateKey(now);
  const isPast = date < today;
  const nowSlot = date === today ? (now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60 - DAY_START_HOUR * 60) / 30 : isPast ? SLOTS_PER_DAY : 0;
  const nextItem = orderedItems.find((item) => item.startSlot !== null && item.startSlot >= nowSlot);
  const draggedItem = drag ? allItems.find((item) => item.id === drag.itemId) : null;

  function displayedItems(value: string) {
    const planned = activeSchedule?.days?.find((plan) => plan.date === value)?.items
      ?? (activeSchedule?.date === value ? activeSchedule.items : itemsByDate[value] ?? []);
    if (!drag || !draggedItem) return planned;
    const withoutDragged = planned.filter((item) => item.id !== drag.itemId);
    return draggedItem.date === value ? [...withoutDragged, draggedItem] : withoutDragged;
  }

  function applySchedule(schedule: DaySchedule, highlightedIds = schedule.changes.map((change) => change.itemId)) {
    setItemsByDate((current) => {
      const next = { ...current };
      if (schedule.days?.length) {
        for (const plan of schedule.days) next[plan.date] = plan.items;
      } else {
        next[schedule.date] = schedule.items;
      }
      return next;
    });
    setChanges(schedule.changes);
    setHighlightedItemIds([...new Set(highlightedIds)]);
    setCanUndo(schedule.canUndo);
    setSolverStatus(schedule.solverStatus);
    setDrag(null);
  }

  async function addItem(item: CalendarItem) {
    try {
      const result = await calendarApi.addItem(item);
      const placed = scheduleItems(result).find((entry) => entry.id === item.id)!;
      const moved = scheduleItems(result).filter((entry) => {
        const old = allItems.find((candidate) => candidate.id === entry.id);
        return old && (old.date !== entry.date || old.startSlot !== entry.startSlot);
      });
      applySchedule(result);
      setFeedback(`Added ${placed.title}${placed.startSlot === null ? " to Needs attention because no valid gap is available" : ` on ${formatDate(placed.date)} at ${formatSlot(placed.startSlot)}`}.${moved.length ? ` Changed ${moved.map((entry) => `${entry.title} to ${placementLabel(entry.startSlot, entry.date)}`).join(", ")} to make room.` : ""}`);
      return null;
    } catch (error) {
      return messageFor(error);
    }
  }

  async function previewItemOptions(item: ProposalItemDraft, candidateStartSlots?: number[]) {
    try {
      const result = await calendarApi.proposals(item, candidateStartSlots);
      setHighlightedItemIds([]);
      setProposalSet(result);
      setSelectedAlternativeId(result.alternatives[0]?.id ?? null);
      setShowNewItemProposal(true);
      setView("calendar");
      setFeedback(`${result.alternatives.length} schedule ${result.alternatives.length === 1 ? "option is" : "options are"} ready. Nothing has been saved.`);
      return null;
    } catch (error) {
      return messageFor(error);
    }
  }

  async function acceptScheduleProposal() {
    if (!proposalSet || !selectedAlternative || commitLock.current) return;
    commitLock.current = true;
    setCommitting(true);
    try {
      const result = await calendarApi.acceptProposal(proposalSet.proposalSetId, selectedAlternative.id);
      applySchedule(result);
      setProposalSet(null);
      setSelectedAlternativeId(null);
      setShowNewItemProposal(false);
      setFeedback(`Applied the ${formatDate(selectedAlternative.date)} ${formatSlot(selectedAlternative.startSlot)} plan. You can undo this schedule update.`);
    } catch (error) {
      setFeedback(messageFor(error));
    } finally {
      commitLock.current = false;
      setCommitting(false);
    }
  }

  async function updateItem(item: CalendarItem) {
    try {
      const previous = allItems.find((entry) => entry.id === item.id)!;
      const preview = await calendarApi.preview({ type: "edit", item });
      const updated = scheduleItems(preview.schedule).find((entry) => entry.id === item.id)!;
      const moved = scheduleItems(preview.schedule).filter((entry) => {
        const old = allItems.find((candidate) => candidate.id === entry.id);
        return old && (old.date !== entry.date || old.startSlot !== entry.startSlot);
      });
      setPendingUpdate({ preview, label: `Edit ${previous.title}` });
      setShowProposedUpdate(true);
      setView("calendar");
      setFeedback(`Edit ready for review.${moved.length ? ` It would reschedule ${moved.map((entry) => `${entry.title} to ${placementLabel(entry.startSlot, entry.date)}`).join(", ")}.` : ` ${updated.title} would stay at ${placementLabel(updated.startSlot, updated.date)}.`} Nothing has been saved.`);
      return null;
    } catch (error) {
      return messageFor(error);
    }
  }

  function editItem(item: CalendarItem) {
    setSelectedId(null);
    setHighlightedItemIds([]);
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

  async function loadSample(targetDate = date) {
    try {
      const result = await calendarApi.seedDay(targetDate);
      applySchedule(result);
      onSelectDate(targetDate);
      setFeedback("Loaded a sample day. Your changes will now persist across refreshes.");
    } catch (error) {
      setFeedback(messageFor(error));
    }
  }

  async function resetDebugSchedule() {
    if (!window.confirm("Replace every task on Sep 11–13 with the debug schedule? This also clears Undo.")) return;
    setResetting(true);
    try {
      const result = await calendarApi.resetDebugSchedule(date);
      setAdding(false);
      setEditing(null);
      setReportingLate(false);
      setMovingId(null);
      setSelectedId(null);
      setProposalSet(null);
      setSelectedAlternativeId(null);
      setShowNewItemProposal(false);
      setPendingUpdate(null);
      applySchedule(result);
      setFeedback("Reset all three days to the debug schedule. Try extending Client review by 60 minutes.");
    } catch (error) {
      setFeedback(messageFor(error));
    } finally {
      setResetting(false);
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

  async function applyPendingUpdate() {
    if (!pendingUpdate) return;
    const failure = await commitAdjustment(pendingUpdate.preview.previewToken);
    if (failure) {
      setFeedback(failure);
      return;
    }
    setPendingUpdate(null);
    setShowProposedUpdate(false);
  }

  function cancelPendingUpdate() {
    setPendingUpdate(null);
    setShowProposedUpdate(false);
    setFeedback("Update canceled. Your saved calendar was not changed.");
  }

  async function undoReschedule() {
    setUndoing(true);
    try {
      const result = await calendarApi.undo(date);
      applySchedule(result);
      setFeedback("Restored all three days to the schedule before the last adjustment.");
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
    setHighlightedItemIds([]);
    setDrag({ itemId: item.id, date: item.date, slot: item.startSlot!, offset });
  }

  function targetSlot(event: DragEvent<HTMLDivElement>) {
    const duration = drag ? allItems.find((item) => item.id === drag.itemId)?.durationSlots ?? 1 : 1;
    return Math.max(0, Math.min(SLOTS_PER_DAY - duration, Math.floor((event.clientY - event.currentTarget.getBoundingClientRect().top) / SLOT_HEIGHT) - (drag?.offset ?? 0)));
  }

  function dragOver(event: DragEvent<HTMLDivElement>, targetDate: string) {
    if (!drag) return;
    event.preventDefault();
    const slot = targetSlot(event);
    event.dataTransfer.dropEffect = dragProposal.preview && slot === drag.slot && targetDate === drag.date ? "move" : "none";
    if (slot !== drag.slot || targetDate !== drag.date) setDrag({ ...drag, date: targetDate, slot });
    const scroll = calendarRef.current;
    if (scroll) {
      const bounds = scroll.getBoundingClientRect();
      if (event.clientY < bounds.top + 48) scroll.scrollTop -= 18;
      else if (event.clientY > bounds.bottom - 48) scroll.scrollTop += 18;
    }
  }

  async function dropTask(event: DragEvent<HTMLDivElement>, targetDate: string) {
    event.preventDefault();
    const proposal = dragProposal.preview;
    const matches = drag && targetDate === drag.date && targetSlot(event) === drag.slot;
    setDrag(null);
    if (!matches || !proposal) {
      setFeedback(dragProposal.error || "Wait for a valid preview before dropping the task. Nothing was saved.");
      return;
    }
    setPendingUpdate({ preview: proposal, label: `Move ${draggedItem?.title ?? "task"}` });
    setShowProposedUpdate(true);
    setFeedback("Move ready for review. Toggle Current and Proposed, then apply or cancel. Nothing has been saved.");
    onSelectDate(targetDate);
  }

  function updateSidebarWidth(width: number, persist = false) {
    const next = clampSidebarWidth(width);
    sidebarWidthRef.current = next;
    setSidebarWidth(next);
    if (persist) window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(next));
  }

  function startSidebarResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (window.innerWidth <= 760) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizingSidebarRef.current = true;
    setResizingSidebar(true);
  }

  function resizeSidebar(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizingSidebarRef.current) updateSidebarWidth(event.clientX);
  }

  function finishSidebarResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!resizingSidebarRef.current) return;
    resizingSidebarRef.current = false;
    setResizingSidebar(false);
    window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidthRef.current));
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function resizeSidebarWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 32 : 8;
    const next = event.key === "ArrowLeft" ? sidebarWidthRef.current - step
      : event.key === "ArrowRight" ? sidebarWidthRef.current + step
        : event.key === "Home" ? SIDEBAR_MIN_WIDTH
          : event.key === "End" ? SIDEBAR_MAX_WIDTH
            : null;
    if (next === null) return;
    event.preventDefault();
    updateSidebarWidth(next, true);
  }

  function resetSidebarWidth() {
    updateSidebarWidth(SIDEBAR_DEFAULT_WIDTH, true);
  }

  return (
    <><main className={resizingSidebar ? "sidebar-is-resizing" : undefined} aria-busy={committing || resetting} inert={committing || resetting}>
      <aside className="control-sidebar" style={{ "--sidebar-width": `${sidebarWidth}px` } as CSSProperties}>
        <div className="compact-brand"><span className="brand-mark">T</span><div><strong>Tetris</strong><small>Sep 11–13 schedule</small></div></div>
        <nav className="view-tabs" aria-label="Main navigation">
          <button className={view === "calendar" ? "active" : ""} aria-current={view === "calendar" ? "page" : undefined} onClick={showCalendar}>Calendar</button>
          <button className={view === "tasks" ? "active" : ""} aria-current={view === "tasks" ? "page" : undefined} onClick={() => setView("tasks")}>Tasks <span>{allItems.length}</span></button>
        </nav>
        <section className="sidebar-section sidebar-demo">
          <p className="eyebrow">PRESENTATION</p>
          <DemoClockControls />
          <button className="debug-reset-button" onClick={resetDebugSchedule} disabled={committing || resetting}>{resetting ? "Resetting…" : "↻ Debug reset"}</button>
        </section>
        <button ref={addButtonRef} className="add-button sidebar-add-button" onClick={() => setAdding(true)} disabled={loading || isPast || !!proposalSet || !!pendingUpdate}>+ Add task</button>
        <button className="late-top-button sidebar-action-button" onClick={() => setReportingLate(true)} disabled={loading || isPast || !!proposalSet || !!pendingUpdate || !items.some((item) => item.startSlot !== null)}>Running late</button>
        <button className="undo-button sidebar-action-button" onClick={undoReschedule} disabled={!canUndo || undoing || !!proposalSet || !!pendingUpdate}>{undoing ? "Restoring…" : canUndo ? "↶ Undo changes" : "↶ Nothing to undo"}</button>
        <div className="feedback" role="status" aria-live="polite">{feedback}</div>
        {drag && <section className="drag-proposal" aria-label="Drag preview" aria-live="polite">
          <strong>{dragProposal.loading ? `Checking ${formatDate(drag.date)} at ${formatSlot(drag.slot)}…` : dragProposal.error ? "This placement is unavailable" : `Preview on ${formatDate(drag.date)} at ${formatSlot(drag.slot)} · drop to review`}</strong>
          <span>{dragProposal.error || "Other flexible tasks can move across the three days. Release outside the calendar or press Escape to cancel."}</span>
          {dragProposal.preview && <ProposedChanges changes={dragProposal.preview.schedule.changes} />}
        </section>}
        {proposalSet && selectedAlternative && <ScheduleProposalPanel proposalSet={proposalSet} selectedId={selectedAlternative.id}
          showingProposed={showNewItemProposal} applying={committing} onSelect={setSelectedAlternativeId} onToggle={setShowNewItemProposal}
          onCancel={() => { setProposalSet(null); setSelectedAlternativeId(null); setShowNewItemProposal(false); setFeedback("Schedule options canceled. Your calendar was not changed."); }}
          onApply={acceptScheduleProposal} />}
        {pendingUpdate && <UpdateReviewPanel label={pendingUpdate.label} changes={pendingUpdate.preview.schedule.changes}
          showingProposed={showProposedUpdate} applying={committing} onToggle={setShowProposedUpdate}
          onCancel={cancelPendingUpdate} onApply={applyPendingUpdate} />}
        {changes.length > 0 && <ChangePanel changes={changes} solverStatus={solverStatus} />}
      </aside>
      <div className="sidebar-resizer" role="separator" aria-label="Resize sidebar" aria-orientation="vertical"
        aria-valuemin={SIDEBAR_MIN_WIDTH} aria-valuemax={SIDEBAR_MAX_WIDTH} aria-valuenow={sidebarWidth} aria-valuetext={`${sidebarWidth} pixels`}
        tabIndex={0} title="Drag to resize · Double-click to reset"
        onPointerDown={startSidebarResize} onPointerMove={resizeSidebar}
        onPointerUp={finishSidebarResize} onPointerCancel={finishSidebarResize}
        onKeyDown={resizeSidebarWithKeyboard} onDoubleClick={resetSidebarWidth}><span aria-hidden="true" /></div>
      <section className="workspace">
        <div className="content">
          {view === "calendar" ? <section className="calendar-panel three-day-calendar" aria-label="Three-day calendar" aria-busy={loading}>
            <div className="calendar-scroll" ref={calendarRef} tabIndex={0} role="region" aria-label="September 11 through 13 calendar, 8 AM to midnight">
              <div className="calendar-wide" style={{ "--slot-height": `${SLOT_HEIGHT}px` } as CSSProperties}>
                <div className="calendar-header"><span>Time</span>{DEMO_DATES.map((value) => <button type="button" key={value} className={`calendar-day-heading ${value === date ? "selected" : ""}`} onClick={() => onSelectDate(value)} aria-pressed={value === date}>
                  <strong>{new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" })}</strong><small>{formatDate(value)}{value === today ? " · Today" : ""}</small>
                </button>)}</div>
                <div className="calendar-body">
                  <div className="time-column">{boundaries.map((slot) => <span key={slot}>{slot % 2 === 0 ? formatSlot(slot) : ""}</span>)}</div>
                  <div className="multi-day-grid">{DEMO_DATES.map((value) => {
                    const columnItems = displayedItems(value);
                    const columnNowSlot = value === today ? (now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60 - DAY_START_HOUR * 60) / 30 : -1;
                    return <div className={`grid day-grid ${value === date ? "selected" : ""}`} key={value} onClick={() => onSelectDate(value)} onDragOver={(event) => dragOver(event, value)} onDrop={(event) => dropTask(event, value)}>
                      {boundaries.slice(0, -1).map((slot) => <div className="grid-line" key={slot} />)}
                      {columnNowSlot >= 0 && columnNowSlot < SLOTS_PER_DAY && <div className="now-line" style={{ top: columnNowSlot * SLOT_HEIGHT }}><i /><span>{now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</span></div>}
                      {columnItems.map((item) => <CalendarCard key={item.id} item={item} onSelect={() => { if (!drag) { onSelectDate(item.date); setSelectedId(item.id); } }}
                        draggable={!proposalSet && !pendingUpdate && item.kind === "flexible" && !item.isPinned && item.startSlot !== null}
                        proposed={outlinedItemIds.has(item.id)}
                        onDragStart={(event) => dragStart(event, item)} onDragEnd={() => setDrag(null)} />)}
                      {drag?.date === value && <div className={`drop-target ${dragProposal.error ? "invalid" : ""}`} style={{ top: drag.slot * SLOT_HEIGHT, height: (draggedItem?.durationSlots ?? 1) * SLOT_HEIGHT }}><strong>{draggedItem?.title}</strong></div>}
                      {!loading && !columnItems.length && <div className="day-empty"><strong>Open day</strong><button type="button" onClick={(event) => { event.stopPropagation(); loadSample(value); }}>Load sample</button></div>}
                    </div>;
                  })}</div>
                </div>
              </div>
            </div>
          </section> : <section className="task-list-panel" aria-labelledby="task-list-title">
            <div className="list-heading"><h2 id="task-list-title">Tasks on {formatDate(date)}</h2><span>{items.length} planned</span></div>
            {orderedItems.map((item) => <div key={item.id} className="task-row">
              <button type="button" className="task-row-open" onClick={() => setSelectedId(item.id)} aria-label={`Open details for ${item.title}`}>
                <span className={`task-swatch ${item.accent}`} aria-hidden="true" />
                <span className="task-row-main"><strong>{item.title}</strong><span>{item.kind === "fixed" ? "Fixed event" : `Flexible task · due ${formatDate(item.deadlineDate ?? item.date)} ${formatSlot(item.deadlineSlot)}`}{item.isPinned ? " · Pinned" : ""}</span></span>
                <span className={`task-row-time ${item.startSlot === null ? "deferred-text" : ""}`}>{placementLabel(item.startSlot)}<small>{item.startSlot === null ? "Deferred" : formatDuration(item.durationSlots)}</small></span>
              </button>
              <span className="task-row-actions">
                <button type="button" className="task-action-button" disabled={!!pendingUpdate} onClick={() => editItem(item)}>Edit</button>
                <button type="button" className="task-action-button task-delete-button" disabled={!!pendingUpdate} onClick={() => removeItem(item)}>Delete</button>
              </span>
            </div>)}
            {!loading && !items.length && <div className="empty-state"><p>Your day is a blank canvas.</p><button className="add-button" disabled={isPast || !!pendingUpdate} onClick={() => setAdding(true)}>Add your first task</button><button className="secondary-button" disabled={!!pendingUpdate} onClick={() => loadSample()}>Load sample day</button></div>}
          </section>}
        </div>
      </section>
      {adding && <ItemForm date={date} onSave={addItem} onPreviewOptions={previewItemOptions} onClose={() => setAdding(false)} />}
      {editing && <ItemForm date={date} item={editing} onSave={updateItem} onClose={() => setEditing(null)} />}
      {reportingLate && <RunningLateDialog items={items} preferredId={nextItem?.id} onSubmit={commitAdjustment} onClose={() => setReportingLate(false)} />}
      {movingId && <RunningLateDialog items={items} preferredId={movingId} mode="move" onSubmit={commitAdjustment} onClose={() => setMovingId(null)} />}
      {selected && <Dialog title={selected.title} onClose={() => setSelectedId(null)}>
        <p className="detail-kind">{selected.kind === "fixed" ? "Fixed event" : "Flexible task"}{selected.isPinned ? " · Pinned" : ""}</p>
        <dl className="item-details"><div><dt>Time</dt><dd>{selected.startSlot === null ? "Deferred — needs attention" : `${formatSlot(selected.startSlot)} – ${formatSlot(selected.startSlot + selected.durationSlots)}`}</dd></div><div><dt>Duration</dt><dd>{formatDuration(selected.durationSlots)}</dd></div>
          {selected.kind === "flexible" && <div><dt>Finish by</dt><dd>{formatDate(selected.deadlineDate ?? selected.date)} {formatSlot(selected.deadlineSlot)}</dd></div>}
          {selected.note && <div><dt>Note</dt><dd>{selected.note}</dd></div>}
        </dl>
        <p className="form-hint">{selected.kind === "fixed" ? "Fixed events always stay at their chosen time." : selected.startSlot === null ? "No valid continuous gap remains before this task's deadline. Edit it or free calendar space so the optimizer can schedule it later." : selected.isPinned ? "Pinned tasks keep this exact time when other items are added." : "Flexible tasks can move when a fixed event needs this time."}</p>
        <div className="dialog-actions"><button className="delete-button" disabled={!!pendingUpdate} onClick={() => removeItem(selected)}>Delete item</button><button className="secondary-button" disabled={!!pendingUpdate} onClick={() => editItem(selected)}>Edit item</button><button className="secondary-button" aria-pressed={selected.isPinned} disabled={selected.startSlot === null || !!pendingUpdate} onClick={() => togglePin(selected)}>{selected.isPinned ? "Unpin item" : "Pin item"}</button>
          {selected.kind === "flexible" && !selected.isPinned && <button className="secondary-button" disabled={isPast || !!pendingUpdate} onClick={() => { setMovingId(selected.id); setSelectedId(null); }}>Move task</button>}
        </div>
      </Dialog>}
    </main>{(committing || resetting) && <div className="saving-overlay" role="status">{resetting ? "Loading the debug schedule…" : "Saving your adjustment…"}</div>}</>
  );
}

function messageFor(error: unknown) {
  return error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function UpdateReviewPanel({ label, changes, showingProposed, applying, onToggle, onCancel, onApply }: {
  label: string;
  changes: ScheduleChange[];
  showingProposed: boolean;
  applying: boolean;
  onToggle: (show: boolean) => void;
  onCancel: () => void;
  onApply: () => void;
}) {
  return <section className="schedule-proposals update-review" aria-labelledby="update-review-heading">
    <div className="proposal-heading">
      <div><p className="eyebrow">NOTHING SAVED YET</p><h2 id="update-review-heading">{label}</h2></div>
      <span>Compare before and after.</span>
    </div>
    <div className="proposal-options update-toggle" role="radiogroup" aria-label="Calendar version">
      <button type="button" role="radio" aria-checked={!showingProposed}
        className={`proposal-option ${!showingProposed ? "selected" : ""}`} onClick={() => onToggle(false)}>
        <span className="proposal-option-label">Before</span><strong>Current schedule</strong>
      </button>
      <button type="button" role="radio" aria-checked={showingProposed}
        className={`proposal-option ${showingProposed ? "selected" : ""}`} onClick={() => onToggle(true)}>
        <span className="proposal-option-label">After</span><strong>Proposed update</strong>
        <small>{changes.length} {changes.length === 1 ? "change" : "changes"}</small>
      </button>
    </div>
    <div className="update-review-detail">
      {showingProposed ? <ProposedChanges changes={changes} /> : <p className="form-hint">Showing the currently saved calendar. The proposed update remains unsaved.</p>}
    </div>
    <div className="proposal-actions">
      <button type="button" className="secondary-button" onClick={onCancel} disabled={applying}>Cancel</button>
      <button type="button" className="add-button" onClick={onApply} disabled={applying}>{applying ? "Applying…" : "Apply update"}</button>
    </div>
  </section>;
}

function ChangePanel({ changes, solverStatus }: { changes: ScheduleChange[]; solverStatus: DaySchedule["solverStatus"] }) {
  return <section className="change-panel" aria-labelledby="change-heading">
    <div className="change-panel-heading"><div><p className="eyebrow">SCHEDULE UPDATE{solverStatus ? ` · ${solverStatus.toUpperCase()}` : ""}</p><h2 id="change-heading">{changes.length} {changes.length === 1 ? "change" : "changes"} across your schedule</h2></div></div>
    {changes.length > 0 && <div className="change-list">{changes.map((change) => <article className={`change-item ${change.changeType}`} key={`${change.itemId}-${change.changeType}`}>
      <span className="change-badge">{change.changeType}</span><div><strong>{change.title}</strong><span>{changeSummary(change)}</span><small>{change.reason}</small></div>
    </article>)}</div>}
  </section>;
}

function changeSummary(change: ScheduleChange) {
  if (change.changeType === "extended") return `${formatDuration(change.fromDurationSlots!)} → ${formatDuration(change.toDurationSlots!)}`;
  if (change.fromDate !== change.toDate || change.fromStartSlot !== change.toStartSlot) return `${placementLabel(change.fromStartSlot, change.fromDate)} → ${placementLabel(change.toStartSlot, change.toDate)}`;
  if (change.fromDurationSlots !== change.toDurationSlots) return `${formatDuration(change.fromDurationSlots!)} → ${formatDuration(change.toDurationSlots!)}`;
  if (change.changeType === "edited") return "Task details updated";
  return "Previous placement restored";
}

function placementLabel(slot: number | null, date?: string | null) {
  return slot === null ? "Needs attention" : `${date ? `${formatDate(date)} ` : ""}${formatSlot(slot)}`;
}
