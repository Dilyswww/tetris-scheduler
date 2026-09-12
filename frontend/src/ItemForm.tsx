import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import type { CalendarItem, ProposalItemDraft } from "./types.ts";
import { SLOTS_PER_DAY } from "./types.ts";
import { earliestStartSlot, formatDuration, formatSlot } from "./time.ts";
import { Dialog } from "./Dialog";

const boundaries = Array.from({ length: SLOTS_PER_DAY + 1 }, (_, slot) => slot);

export function ItemForm({ date, item: initialItem, onSave, onPreviewOptions, onClose }: {
  date: string;
  item?: CalendarItem;
  onSave: (item: CalendarItem) => Promise<string | null>;
  onPreviewOptions?: (item: ProposalItemDraft, candidateStartSlots?: number[]) => Promise<string | null>;
  onClose: () => void;
}) {
  const editing = initialItem !== undefined;
  const [now, setNow] = useState(() => new Date());
  const cutoff = editing ? 0 : earliestStartSlot(date, now);
  const initialStart = initialItem?.startSlot ?? Math.min(31, Math.max(12, cutoff));
  const [kind, setKind] = useState<CalendarItem["kind"]>(initialItem?.kind ?? "flexible");
  const [title, setTitle] = useState(initialItem?.title ?? "");
  const [note, setNote] = useState(initialItem?.note ?? "");
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(Math.min(SLOTS_PER_DAY, initialStart + (initialItem?.durationSlots ?? 2)));
  const [alternativeStart, setAlternativeStart] = useState<number | "">("");
  const [duration, setDuration] = useState(initialItem?.durationSlots ?? 2);
  const [deadline, setDeadline] = useState(initialItem?.kind === "flexible"
    ? initialItem.deadlineSlot
    : initialItem
      ? Math.min(SLOTS_PER_DAY, Math.max(18, initialStart + initialItem.durationSlots))
      : Math.min(SLOTS_PER_DAY, Math.max(18, cutoff + 2)));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fixedDuration = end - start;
  const optionsInvalid = !editing && kind === "fixed" && !!onPreviewOptions
    && alternativeStart !== ""
    && (alternativeStart === start || alternativeStart < cutoff || alternativeStart + fixedDuration > SLOTS_PER_DAY);
  const flexibleOptionsInvalid = !editing && kind === "flexible" && !!onPreviewOptions
    && (duration > deadline || cutoff + duration > deadline);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing && kind === "fixed" && start < earliestStartSlot(date)) {
      setError("Choose a start time that has not elapsed.");
      setNow(new Date());
      return;
    }
    if (!editing && kind === "fixed" && onPreviewOptions) {
      if (alternativeStart !== "" && (alternativeStart === start || alternativeStart < earliestStartSlot(date) || alternativeStart + fixedDuration > SLOTS_PER_DAY)) {
        setError("Choose a different alternative time where the full event fits.");
        setNow(new Date());
        return;
      }
      setSaving(true);
      setError(null);
      const failure = await onPreviewOptions({
        kind: "fixed", id: crypto.randomUUID(), title: title.trim(), note: note.trim(), date,
        durationSlots: fixedDuration, accent: "blue",
      }, alternativeStart === "" ? [start] : [start, alternativeStart]);
      setSaving(false);
      if (failure) setError(failure); else onClose();
      return;
    }
    if (!editing && kind === "flexible" && onPreviewOptions) {
      if (duration > deadline) {
        setError("Choose a deadline that leaves enough time for this task.");
        return;
      }
      setSaving(true);
      setError(null);
      const failure = await onPreviewOptions({
        kind: "flexible", id: crypto.randomUUID(), title: title.trim(), note: note.trim(), date,
        durationSlots: duration, deadlineSlot: deadline, accent: "purple",
      });
      setSaving(false);
      if (failure) setError(failure); else onClose();
      return;
    }
    const base = { id: initialItem?.id ?? crypto.randomUUID(), title: title.trim(), note: note.trim(), date, isPinned: initialItem?.isPinned ?? false };
    const item: CalendarItem = kind === "fixed"
      ? { ...base, kind, startSlot: start, durationSlots: end - start, accent: initialItem?.accent ?? "blue" }
      : { ...base, kind, startSlot: initialItem?.startSlot ?? null, durationSlots: duration, deadlineSlot: deadline, accent: initialItem?.accent ?? "purple" };
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
        <p className="form-hint">{kind === "fixed" ? editing ? "Fixed events stay at the time you choose." : "Preview the schedule at this exact time, or add an optional alternative to compare two plans." : editing ? "We'll find a continuous gap before your deadline." : "The optimizer will propose up to two distinct placements before anything is saved."}</p>
        {!editing && cutoff === SLOTS_PER_DAY && <p className="form-hint">No future slots remain in this day, so a new schedule option cannot be generated.</p>}
        <div className="form-row">
          {kind === "fixed" ? <>
            <label>Start time<select value={start} onChange={(event) => { const next = Number(event.target.value); setStart(next); if (end <= next) setEnd(next + 1); }}>
              {boundaries.slice(0, -1).map((slot) => <option key={slot} value={slot} disabled={slot < cutoff}>{formatSlot(slot)}</option>)}
            </select></label>
            <label>End time<select value={end} onChange={(event) => setEnd(Number(event.target.value))}>
              {boundaries.filter((slot) => slot > start).map((slot) => <option key={slot} value={slot}>{formatSlot(slot)}{slot === 32 ? " (midnight)" : ""}</option>)}
            </select></label>
            {!editing && onPreviewOptions && <label className="full-row">Alternative start <span className="optional">(optional)</span><select value={alternativeStart} onChange={(event) => setAlternativeStart(event.target.value === "" ? "" : Number(event.target.value))}>
              <option value="">No alternative</option>
              {boundaries.slice(0, -1).map((slot) => <option key={slot} value={slot} disabled={slot < cutoff || slot === start || slot + (end - start) > SLOTS_PER_DAY}>{formatSlot(slot)}</option>)}
            </select></label>}
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
        <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Cancel</button><button className="add-button" type="submit" disabled={saving || optionsInvalid || flexibleOptionsInvalid || (!editing && kind === "fixed" && start < cutoff)}>{saving ? "Finding options…" : editing ? "Reschedule task" : onPreviewOptions ? kind === "fixed" && alternativeStart === "" ? "Preview plan" : "Preview options" : kind === "fixed" ? "Add event" : "Schedule task"}</button></div>
      </form>
    </Dialog>
  );
}
