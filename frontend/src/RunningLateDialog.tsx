import { useState } from "react";
import type { FormEvent } from "react";
import type { CalendarItem, OptimizerOperation } from "./types.ts";
import { SLOTS_PER_DAY } from "./types.ts";
import { formatDuration, formatSlot, localDateKey } from "./time.ts";
import { Dialog } from "./Dialog";
import { ProposedChanges } from "./ProposedChanges";
import { useOptimizerPreview } from "./useOptimizerPreview";

export function RunningLateDialog({ items, preferredId, mode = "extend", onSubmit, onClose }: {
  items: CalendarItem[];
  preferredId?: string;
  mode?: "extend" | "move";
  onSubmit: (previewToken: string) => Promise<string | null>;
  onClose: () => void;
}) {
  const eligible = items.filter((item) => mode === "move"
    ? item.kind === "flexible" && !item.isPinned
    : item.startSlot !== null && item.startSlot + item.durationSlots < (item.kind === "flexible" ? item.deadlineSlot : SLOTS_PER_DAY));
  const [itemId, setItemId] = useState(eligible.find((item) => item.id === preferredId)?.id || eligible[0]?.id || "");
  const [amount, setAmount] = useState(1);
  const [targetSlot, setTargetSlot] = useState(eligible.find((item) => item.id === preferredId)?.startSlot ?? 0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const selected = eligible.find((item) => item.id === itemId);
  const limit = selected ? (selected.kind === "flexible" ? selected.deadlineSlot : SLOTS_PER_DAY) - selected.startSlot! - selected.durationSlots : 0;
  const options = [1, 2, 3, 4].filter((slots) => slots <= limit);
  const additionalSlots = options.includes(amount) ? amount : options[0] || 1;
  const operation: OptimizerOperation | null = !selected ? null : mode === "move"
    ? { type: "move", itemId, targetStartSlot: targetSlot }
    : { type: "extend", itemId, additionalSlots };
  const { preview, error: previewError, loading } = useOptimizerPreview(operation, items, retry);
  const now = new Date();
  const cutoff = selected && selected.date === localDateKey(now) ? Math.max(0, Math.ceil((now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60 - 480) / 30)) : 0;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!preview || saving) return;
    setSaving(true);
    setError(null);
    const failure = await onSubmit(preview.previewToken);
    setSaving(false);
    if (failure) { setError(failure); setRetry((value) => value + 1); } else onClose();
  }

  return <Dialog title={mode === "move" ? "Move a task" : "Running late?"} onClose={() => { if (!saving) onClose(); }}>
    <form className="item-form" onSubmit={submit}>
      {eligible.length ? <>
        <label>Which item?<select autoFocus disabled={saving} value={itemId} onChange={(event) => { setItemId(event.target.value); setAmount(1); setError(null); }}>
          {eligible.map((item) => <option key={item.id} value={item.id}>{item.title} — {item.startSlot === null ? "Unscheduled" : formatSlot(item.startSlot)}</option>)}
        </select></label>
        {mode === "extend" ? <label>Extra time<select disabled={saving} value={additionalSlots} onChange={(event) => { setAmount(Number(event.target.value)); setError(null); }}>
          {options.map((slots) => <option key={slots} value={slots}>{formatDuration(slots)}</option>)}
        </select></label> : <label>Move to<select disabled={saving} value={targetSlot} onChange={(event) => { setTargetSlot(Number(event.target.value)); setError(null); }}>
          {Array.from({ length: SLOTS_PER_DAY }, (_, slot) => <option key={slot} value={slot} disabled={slot < cutoff}>{formatSlot(slot)}</option>)}
        </select></label>}
        <p className="form-hint">{mode === "move" ? "Reserve this time and rearrange other flexible tasks around it." : "Keep this item's start and extend its duration. Elapsed time is unavailable."} Review all changes before applying.</p>
        <div role="status" aria-live="polite">{loading ? "Finding a proposed schedule…" : preview ? "Proposed changes · nothing saved yet" : ""}</div>
        {preview && <ProposedChanges changes={preview.schedule.changes} />}
      </> : <p className="form-hint">No eligible items. Add a flexible task or choose an item with room to extend.</p>}
      {(error || previewError) && <p role="alert" className="form-error">{error || previewError}</p>}
      <div className="dialog-actions"><button type="button" className="secondary-button" onClick={onClose} disabled={saving}>Cancel</button><button className="late-confirm-button" type="submit" disabled={!preview || saving}>{saving ? "Saving…" : "Apply changes"}</button></div>
    </form>
  </Dialog>;
}
