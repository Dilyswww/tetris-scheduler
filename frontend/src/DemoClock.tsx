import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { calendarApi } from "./api";
import { DEMO_DATES } from "./types";
import type { DemoClock } from "./types";

const DemoContext = createContext<{ clock: DemoClock; now: Date; setTime: (value: string) => Promise<void> } | null>(null);

export function useDemoClock() {
  const context = useContext(DemoContext);
  if (!context) throw new Error("The demo clock must be initialized.");
  return context;
}

export function DemoClockProvider({ children }: { children: ReactNode }) {
  const [clock, setClock] = useState<DemoClock | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    let active = true;
    setError("");
    calendarApi.startDemo().then((value) => { if (active) setClock(value); }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Could not start the demo.");
    });
    return () => { active = false; };
  }, [attempt]);
  useEffect(() => {
    if (!clock) return;
    let active = true;
    const timer = window.setInterval(() => {
      const requestGeneration = generation.current;
      calendarApi.getClock().then((value) => {
        if (active && requestGeneration === generation.current) setClock((current) => current && current.revision >= value.revision ? current : value);
      }).catch(() => { /* Mutations report connection errors; keep the last known clock. */ });
    }, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [clock !== null]);
  async function setTime(value: string) {
    generation.current += 1;
    const updated = await calendarApi.setClock(value);
    setClock((current) => current && current.revision > updated.revision ? current : updated);
  }
  if (!clock) return <div className="demo-loading" role="status">{error || "Loading the three-day demo…"}{error && <button onClick={() => setAttempt((value) => value + 1)}>Retry</button>}</div>;
  // The API supplies New York wall time without an offset. Render that same
  // wall time on presentation machines in any local time zone.
  return <DemoContext.Provider value={{ clock, now: new Date(clock.now), setTime }}>{children}</DemoContext.Provider>;
}

export function DemoClockControls() {
  const { clock, now, setTime } = useDemoClock();
  const [date, setDate] = useState(clock.now.slice(0, 10));
  const [time, setInputTime] = useState(clock.now.slice(11, 16));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError("");
    try { await setTime(`${date}T${time}:00`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not change the demo time."); }
    finally { setSaving(false); }
  }
  return <details className="demo-clock">
    <summary><span>Paused · {now.toLocaleDateString("en-US", { month: "short", day: "numeric" })} · {now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })} <small>NY</small></span><strong>Edit time</strong></summary>
    <div className="demo-clock-editor"><strong>Presentation clock · New York</strong>
    <form onSubmit={submit}>
      <label>Current day<select value={date} disabled={saving} onChange={(event) => setDate(event.target.value)}>{DEMO_DATES.map((day) => <option key={day} value={day}>{day.slice(5)}</option>)}</select></label>
      <label>Current time<input type="time" required step="60" value={time} disabled={saving} onChange={(event) => setInputTime(event.target.value)} /></label>
      <button className="secondary-button" disabled={saving}>{saving ? "Setting…" : "Set demo time"}</button>
    </form>
    {error && <p role="alert" className="form-error">{error}</p>}
    </div>
  </details>;
}
