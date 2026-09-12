import { useState } from "react";
import type { FormEvent } from "react";
import type { CalendarItem } from "./types.ts";
import { SLOTS_PER_DAY } from "./types.ts";
import { formatDuration, formatSlot } from "./time.ts";
import { Dialog } from "./Dialog";

const boundaries = Array.from({ length: SLOTS_PER_DAY + 1 }, (_, slot) => slot);

export function ItemForm({ date, item: initialItem, onSave, onClose }: { date: string; item?: CalendarItem; onSave: (item: CalendarItem) => Promise<string | null>; onClose: () => void }) {
  const editing = initialItem !== undefined;
  const initialStart = initialItem?.startSlot ?? 12;
  const [kind, setKind] = useState<CalendarItem["kind"]>(initialItem?.kind ?? "flexible");
  const [title, setTitle] = useState(initialItem?.title ?? "");
  const [note, setNote] = useState(initialItem?.note ?? "");
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialStart + (initialItem?.durationSlots ?? 2));
  const [duration, setDuration] = useState(initialItem?.durationSlots ?? 2);
  const [deadline, setDeadline] = useState(initialItem?.kind === "flexible" ? initialItem.deadlineSlot : 18);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const base = { id: initialItem?.id ?? crypto.randomUUID(), title: title.trim(), note: note.trim(), date, isPinned: initialItem?.isPinned ?? false };
    const item: CalendarItem = kind === "fixed"
      ? { ...base, kind, startSlot: start, durationSlots: end - start, accent: initialItem?.accent ?? "blue" }
      : { ...base, kind, startSlot: initialItem?.kind === "flexible" ? initialItem.startSlot : null, durationSlots: duration, deadlineSlot: deadline, accent: initialItem?.accent ?? "purple" };
    setSaving(true);
    setError(null);
    const failure = await onSave(item);
    setSaving(false);
    if (failure) setError(failure); else onClose();
  }

  return (
    <Dialog title={editing ? "Edit item" : "Add to your day"} onClose={onClose}>
      <form onSubmit={submit} className="item-form">
        <label>Title<input autoFocus required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What needs to happen?" /></label>
        <label>Item type<select value={kind} onChange={(event) => { setKind(event.target.value as CalendarItem["kind"]); setError(null); }}>
          <option value="flexible">Flexible task</option><option value="fixed">Fixed event</option>
        </select></label>
        <p className="form-hint">{kind === "fixed" ? "Fixed events stay at the time you choose." : "We'll find a continuous gap before your deadline."}</p>
        <div className="form-row">
          {kind === "fixed" ? <>
            <label>Start time<select value={start} onChange={(event) => { const next = Number(event.target.value); setStart(next); if (end <= next) setEnd(next + 1); }}>
              {boundaries.slice(0, -1).map((slot) => <option key={slot} value={slot}>{formatSlot(slot)}</option>)}
            </select></label>
            <label>End time<select value={end} onChange={(event) => setEnd(Number(event.target.value))}>
              {boundaries.filter((slot) => slot > start).map((slot) => <option key={slot} value={slot}>{formatSlot(slot)}{slot === 32 ? " (midnight)" : ""}</option>)}
            </select></label>
          </> : <>
            <label>Duration<select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>
              {boundaries.slice(1).map((slot) => <option key={slot} value={slot}>{formatDuration(slot)}</option>)}
            </select></label>
            <label>Finish by<select value={deadline} onChange={(event) => setDeadline(Number(event.target.value))}>
              {boundaries.slice(1).map((slot) => <option key={slot} value={slot}>{formatSlot(slot)}{slot === 32 ? " (midnight)" : ""}</option>)}
            </select></label>
          </>}
        </div>
        <label>Note <span className="optional">(optional)</span><input maxLength={240} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Location, link, or a little context" /></label>
        {error && <p role="alert" className="form-error">{error}</p>}
        <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Cancel</button><button className="add-button" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Reschedule task" : kind === "fixed" ? "Add event" : "Schedule task"}</button></div>
      </form>
    </Dialog>
  );
}
