import type { ProposalAlternative, ScheduleChange, ProposalSet } from "./types";
import { SLOTS_PER_DAY } from "./types";
import { formatDuration, formatSlot } from "./time";

const MIN_VISIBLE_SLOTS = 8;

function visibleTimeline(startSlots: number[], endSlots: number[]) {
  if (startSlots.length === 0) return { start: 0, end: MIN_VISIBLE_SLOTS };
  const firstItem = Math.min(...startSlots);
  const lastItem = Math.max(...endSlots);
  let start = Math.max(0, Math.floor((firstItem - 1) / 2) * 2);
  let end = Math.min(SLOTS_PER_DAY, Math.ceil((lastItem + 1) / 2) * 2);
  const missingSlots = MIN_VISIBLE_SLOTS - (end - start);
  if (missingSlots > 0) {
    const before = Math.min(start, Math.floor(missingSlots / 2));
    start -= before;
    end = Math.min(SLOTS_PER_DAY, end + missingSlots - before);
    start = Math.max(0, end - MIN_VISIBLE_SLOTS);
  }
  return { start, end };
}

function timelineMarks(start: number, end: number) {
  const interval = end - start <= 12 ? 2 : 4;
  const marks = [start];
  for (let slot = Math.ceil((start + 1) / interval) * interval; slot < end; slot += interval) marks.push(slot);
  if (marks.at(-1) !== end) marks.push(end);
  return marks;
}

function describeChange(change: ScheduleChange) {
  if (change.changeType === "added") return `Added at ${formatSlot(change.toStartSlot!)}`;
  if (change.changeType === "deferred") return "Moved out of today's plan";
  if (change.fromStartSlot === null) return `Scheduled at ${formatSlot(change.toStartSlot!)}`;
  if (change.toStartSlot === null) return "Unscheduled";
  return `${formatSlot(change.fromStartSlot)} → ${formatSlot(change.toStartSlot)}`;
}

function MiniSchedule({ option }: { option: ProposalAlternative }) {
  const changedIds = new Set(option.schedule.changes.map((change) => change.itemId));
  const scheduled = option.schedule.items.filter((item) => item.startSlot !== null);
  const deferred = option.schedule.items.filter((item) => item.startSlot === null);
  const timeline = visibleTimeline(
    scheduled.map((item) => item.startSlot!),
    scheduled.map((item) => item.startSlot! + item.durationSlots),
  );
  const visibleSlots = timeline.end - timeline.start;
  const timeMarks = timelineMarks(timeline.start, timeline.end);
  const calendarHeight = Math.min(540, Math.max(240, visibleSlots * 20));
  const position = (slot: number) => `${(slot - timeline.start) / visibleSlots * 100}%`;

  return <>
    <div className="mini-calendar" style={{ height: calendarHeight }} aria-label={`Calendar preview from ${formatSlot(timeline.start)} to ${formatSlot(timeline.end)}`}>
      <div className="mini-time-axis" aria-hidden="true">
        {timeMarks.map((slot) => <span key={slot} style={{ top: position(slot) }}>{formatSlot(slot)}</span>)}
      </div>
      <div className="mini-calendar-grid">
        {timeMarks.map((slot) => <span key={slot} className="mini-grid-line" style={{ top: position(slot) }} aria-hidden="true" />)}
        {scheduled.map((item) => {
          const startSlot = item.startSlot!;
          const endSlot = startSlot + item.durationSlots;
          return <div key={item.id}
            className={`mini-calendar-event ${item.kind} ${item.accent} ${changedIds.has(item.id) ? "is-changed" : ""}`}
            style={{ top: position(startSlot), height: `${item.durationSlots / visibleSlots * 100}%` }}
            aria-label={`${item.title}, ${formatSlot(startSlot)} to ${formatSlot(endSlot)}${changedIds.has(item.id) ? ", changed in this plan" : ""}`}>
            <strong>{item.title}</strong>
            {item.durationSlots > 1 && <span>{formatSlot(startSlot)}–{formatSlot(endSlot)}</span>}
          </div>;
        })}
      </div>
    </div>
    {deferred.length > 0 && <div className="mini-deferred"><strong>Deferred</strong>{deferred.map((item) => <span key={item.id}>{item.title}</span>)}</div>}
    <div className="mini-change-summary" aria-label="Changes in this proposal">
      {option.schedule.changes.map((change) => <span key={change.itemId}><strong>{change.title}</strong> {describeChange(change)}</span>)}
    </div>
  </>;
}

export function ScheduleProposalPanel({ proposalSet, selectedId, applying, onSelect, onCancel, onApply }: {
  proposalSet: ProposalSet;
  selectedId: string;
  applying: boolean;
  onSelect: (id: string) => void;
  onCancel: () => void;
  onApply: () => void;
}) {
  const selected = proposalSet.alternatives.find((option) => option.id === selectedId) ?? proposalSet.alternatives[0];
  return <section className="schedule-proposals" aria-labelledby="proposal-heading">
    <div className="proposal-heading">
      <div><p className="eyebrow">NOTHING SAVED YET</p><h2 id="proposal-heading">Choose your new plan</h2></div>
      <span>Preview each option before applying it.</span>
    </div>
    <div className="proposal-layout">
      <div className="proposal-options" role="radiogroup" aria-label="Schedule options">
        {proposalSet.alternatives.map((option, index) => <button key={option.id} type="button" role="radio"
          aria-checked={option.id === selected.id} className={`proposal-option ${option.id === selected.id ? "selected" : ""}`}
          onClick={() => onSelect(option.id)}>
          <span className="proposal-option-label">Option {String.fromCharCode(65 + index)} · {formatSlot(option.startSlot)}</span>
          <strong>{option.label}</strong>
          <small>{option.metrics.movedTaskCount} moved · {option.metrics.deferredTaskCount} deferred · {formatDuration(option.metrics.totalShiftSlots)} total shift</small>
        </button>)}
      </div>
      <div className="proposal-detail">
        <div className="proposal-detail-heading"><strong>Previewing {formatSlot(selected.startSlot)}</strong><span><i /> Changed in this plan</span></div>
        <MiniSchedule option={selected} />
      </div>
    </div>
    <div className="proposal-actions"><button type="button" className="secondary-button" onClick={onCancel} disabled={applying}>Cancel</button><button type="button" className="add-button" onClick={onApply} disabled={applying}>{applying ? "Applying…" : `Apply ${formatSlot(selected.startSlot)} plan`}</button></div>
  </section>;
}
