import { useEffect, useState } from "react";
import { calendarApi } from "./api";
import type { OptimizerOperation, SchedulePreview } from "./types";

// Keys prevent even one render of an old response at a new drag position.
export function useOptimizerPreview(operation: OptimizerOperation | null, calendarVersion: unknown, retry = 0) {
  const key = JSON.stringify(operation);
  const [result, setResult] = useState<{ key: string; version: unknown; retry: number; preview: SchedulePreview | null; error: string | null } | null>(null);
  useEffect(() => {
    if (key === "null") return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      calendarApi.preview(JSON.parse(key) as OptimizerOperation, controller.signal).then(
        (preview) => { if (!controller.signal.aborted) setResult({ key, version: calendarVersion, retry, preview, error: null }); },
        (error: unknown) => { if (!controller.signal.aborted) setResult({ key, version: calendarVersion, retry, preview: null, error: error instanceof Error ? error.message : "Could not preview this change." }); },
      );
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key, calendarVersion, retry]);
  const current = result?.key === key && result.version === calendarVersion && result.retry === retry ? result : null;
  return { preview: current?.preview ?? null, error: current?.error ?? null, loading: operation !== null && !current };
}
