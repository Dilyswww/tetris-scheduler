import type { ScheduleChange } from "./types";
import { formatDate, formatDuration, formatSlot } from "./time";

export function ProposedChanges({ changes }: { changes: ScheduleChange[] }) {
  return <div className="proposal-changes" aria-label="Proposed changes">
    {changes.map((change) => <article key={change.itemId}>
      <strong>{change.title} <span className="change-badge">{change.changeType}</span></strong>
      <span>{formatDate(change.fromDate)} {interval(change.fromStartSlot, change.fromDurationSlots)} → {change.toStartSlot === null ? "Deferred · needs attention" : `${formatDate(change.toDate)} ${interval(change.toStartSlot, change.toDurationSlots)}`}
        {change.fromDurationSlots !== change.toDurationSlots && ` · ${formatDuration(change.fromDurationSlots!)} → ${formatDuration(change.toDurationSlots!)}`}</span>
      <small>{change.reason}</small>
    </article>)}
  </div>;
}

function interval(start: number | null, duration: number | null) {
  return start === null ? "Unscheduled" : `${formatSlot(start)}–${formatSlot(start + (duration ?? 0))}`;
}
