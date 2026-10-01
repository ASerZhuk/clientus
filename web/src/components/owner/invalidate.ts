import type { QueryClient } from "@tanstack/react-query";

/** Anything that changes bookings, blocks or money refreshes the schedule, stats and slots together. */
export function refreshSchedule(qc: QueryClient, slug: string) {
  qc.invalidateQueries({ queryKey: ["owner-schedule", slug] });
  qc.invalidateQueries({ queryKey: ["owner-stats", slug] });
  qc.invalidateQueries({ queryKey: ["owner-booking", slug] });
  qc.invalidateQueries({ queryKey: ["slots", slug] });
}
