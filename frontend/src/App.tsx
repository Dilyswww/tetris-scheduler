import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { CalendarItem } from "./types.ts";
import { DAY_START_HOUR, SLOTS_PER_DAY } from "./types.ts";
import { formatDuration, formatSlot, localDateKey } from "./time.ts";
import { createSeedItems } from "./seed.ts";
import { scheduleItems } from "./scheduler.ts";
import { ItemForm } from "./ItemForm";
import { Dialog } from "./Dialog";

const SLOT_HEIGHT = 48;
const boundaries = Array.from({ length: SLOTS_PER_DAY + 1 }, (_, slot) => slot);

function CalendarCard({ item, onSelect }: { item: CalendarItem; onSelect: () => void }) {
  if (item.startSlot === null) return null;
  return (
    <button type="button" className={`calendar-card ${item.kind} ${item.accent} ${item.isPinned ? "is-pinned" : ""}`}
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
  const [items, setItems] = useState(() => createSeedItems(date));
  const [view, setView] = useState<"calendar" | "tasks">("calendar");
  const [adding, setAdding] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [now, setNow] = useState(() => new Date());
  const calendarRef = useRef<HTMLDivElement>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const selected = items.find((item) => item.id === selectedId);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const plannedSlots = items.reduce((sum, item) => sum + item.durationSlots, 0);
  const focusSlots = items.filter((item) => item.kind === "flexible").reduce((sum, item) => sum + item.durationSlots, 0);
  const openSlots = SLOTS_PER_DAY - plannedSlots;
  const orderedItems = [...items].sort((a, b) => (a.startSlot ?? 32) - (b.startSlot ?? 32));
  const nowSlot = (now.getHours() * 60 + now.getMinutes() - DAY_START_HOUR * 60) / 30;
  const showNow = localDateKey(now) === date && nowSlot >= 0 && nowSlot < SLOTS_PER_DAY;
  const nextItem = orderedItems.find((item) => item.startSlot !== null && item.startSlot >= nowSlot);

  function addItem(item: CalendarItem) {
    const result = scheduleItems([...items, item]);
    if (!result.ok) return result.error;
    const placed = result.items.find((entry) => entry.id === item.id)!;
    const moved = items.filter((entry) => result.items.find((next) => next.id === entry.id)?.startSlot !== entry.startSlot);
    setItems(result.items);
    setFeedback(`Added ${placed.title} at ${formatSlot(placed.startSlot!)}.${moved.length ? ` Moved ${moved.map((entry) => `${entry.title} to ${formatSlot(result.items.find((next) => next.id === entry.id)!.startSlot!)}`).join(", ")} to make room.` : ""}`);
    return null;
  }

  function togglePin(item: CalendarItem) {
    setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, isPinned: !entry.isPinned } : entry));
    setFeedback(`${item.title} ${item.isPinned ? "unpinned" : `pinned at ${formatSlot(item.startSlot!)}`}.${item.kind === "fixed" ? " Fixed events always stay in place." : ""}`);
  }

  function removeItem(item: CalendarItem) {
    setItems((current) => current.filter((entry) => entry.id !== item.id));
    setSelectedId(null);
    setFeedback(`Deleted ${item.title}.`);
    addButtonRef.current?.focus();
  }

  function showCalendar() {
    setView("calendar");
    calendarRef.current?.scrollTo({ top: 0 });
  }

  return (
    <main>
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
          <div className="top-actions"><button className="today-button" onClick={showCalendar}>Today</button><button ref={addButtonRef} className="add-button" onClick={() => setAdding(true)}>+ Add task</button></div>
        </header>
        <div className="feedback" role="status" aria-live="polite">{feedback || "Select an item to see its details, pin it, or delete it."}</div>
        <div className="content">
          {view === "calendar" ? <section className="calendar-panel" aria-label="Day calendar">
            <div className="calendar-header"><span>Time</span><strong>{weekday} <span className="grid-caption">· 30-minute slots</span></strong></div>
            <div className="calendar-scroll" ref={calendarRef} tabIndex={0} role="region" aria-label="Calendar, 8 AM to midnight">
              <div className="calendar-body" style={{ "--slot-height": `${SLOT_HEIGHT}px` } as CSSProperties}>
                <div className="time-column">{boundaries.map((slot) => <span key={slot}>{slot % 2 === 0 ? formatSlot(slot) : ""}</span>)}</div>
                <div className="grid">
                  {boundaries.slice(0, -1).map((slot) => <div className="grid-line" key={slot} />)}
                  {showNow && <div className="now-line" style={{ top: nowSlot * SLOT_HEIGHT }}><i /><span>{now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</span></div>}
                  {orderedItems.map((item) => <CalendarCard key={item.id} item={item} onSelect={() => setSelectedId(item.id)} />)}
                </div>
              </div>
            </div>
          </section> : <section className="task-list-panel" aria-labelledby="task-list-title">
            <div className="list-heading"><h2 id="task-list-title">Your tasks & events</h2><span>{items.length} planned</span></div>
            {orderedItems.map((item) => <button key={item.id} className="task-row" onClick={() => setSelectedId(item.id)}>
              <span className={`task-swatch ${item.accent}`} aria-hidden="true" /><span className="task-row-main"><strong>{item.title}</strong><span>{item.kind === "fixed" ? "Fixed event" : `Flexible · due ${formatSlot(item.deadlineSlot)}`}{item.isPinned ? " · Pinned" : ""}</span></span>
              <span className="task-row-time">{formatSlot(item.startSlot!)}<small>{formatDuration(item.durationSlots)}</small></span>
            </button>)}
            {!items.length && <div className="empty-state"><p>Your day is a blank canvas.</p><button className="add-button" onClick={() => setAdding(true)}>Add your first task</button></div>}
          </section>}
          <aside className="right-panel">
            <section className="notice-card"><div className="notice-icon" aria-hidden="true">✦</div><div><p className="eyebrow">{openSlots ? "ROOM TO BREATHE" : "FULL DAY"}</p><strong>{formatDuration(openSlots)} available.</strong><span>{openSlots} open half-hour {openSlots === 1 ? "slot" : "slots"}.</span></div></section>
            <section className="legend-card"><p className="eyebrow">SCHEDULE</p>
              <div><i className="legend-dot fixed-dot" /> Fixed events <span>Can't move</span></div><div><i className="legend-dot flex-dot" /> Flexible tasks <span>Can adapt</span></div><div><i className="legend-dot pin-dot" /> Pinned <span>Keep in place</span></div>
            </section>
            <section className="up-next"><div className="section-title"><p className="eyebrow">UP NEXT</p><button onClick={() => setView("tasks")}>View all</button></div>
              {nextItem ? <button className="next-card" onClick={() => setSelectedId(nextItem.id)}><span className="event-icon" aria-hidden="true">▣</span><span className="next-copy"><strong>{nextItem.title}</strong><span>{formatSlot(nextItem.startSlot!)} · {formatDuration(nextItem.durationSlots)}</span></span></button> : <p className="quiet-copy">No more items starting today.</p>}
            </section>
          </aside>
        </div>
      </section>
      {adding && <ItemForm date={date} onAdd={addItem} onClose={() => setAdding(false)} />}
      {selected && <Dialog title={selected.title} onClose={() => setSelectedId(null)}>
        <p className="detail-kind">{selected.kind === "fixed" ? "Fixed event" : "Flexible task"}{selected.isPinned ? " · Pinned" : ""}</p>
        <dl className="item-details"><div><dt>Time</dt><dd>{formatSlot(selected.startSlot!)} – {formatSlot(selected.startSlot! + selected.durationSlots)}</dd></div><div><dt>Duration</dt><dd>{formatDuration(selected.durationSlots)}</dd></div>
          {selected.kind === "flexible" && <div><dt>Finish by</dt><dd>{formatSlot(selected.deadlineSlot)}</dd></div>}
          {selected.note && <div><dt>Note</dt><dd>{selected.note}</dd></div>}
        </dl>
        <p className="form-hint">{selected.kind === "fixed" ? "Fixed events always stay at their chosen time." : selected.isPinned ? "Pinned tasks keep this exact time when other items are added." : "Flexible tasks can move when a fixed event needs this time."}</p>
        <div className="dialog-actions"><button className="delete-button" onClick={() => removeItem(selected)}>Delete item</button><button className="secondary-button" aria-pressed={selected.isPinned} onClick={() => togglePin(selected)}>{selected.isPinned ? "Unpin item" : "Pin item"}</button></div>
      </Dialog>}
    </main>
  );
}
