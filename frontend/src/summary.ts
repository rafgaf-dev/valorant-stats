import type { Window } from "./api";

export const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export type MetricKey = "kd" | "winRate" | "headshotRate";

export function isStale(generatedAt: string, now: Date = new Date()): boolean {
	return now.getTime() - new Date(generatedAt).getTime() > STALE_AFTER_MS;
}

export function formatMetric(key: MetricKey, value: number | null): string {
	if (value === null) return "—";
	return key === "kd" ? value.toFixed(2) : `${(value * 100).toFixed(1)}%`;
}

/** Signed difference, in the metric's own unit: "+0.12" or "−3.4 pts". */
export function formatDelta(key: MetricKey, delta: number | null): string {
	if (delta === null) return "—";
	const sign = delta > 0 ? "+" : delta < 0 ? "−" : "±";
	const magnitude = Math.abs(delta);
	return key === "kd" ? `${sign}${magnitude.toFixed(2)}` : `${sign}${(magnitude * 100).toFixed(1)} pts`;
}

export function metricDelta(key: MetricKey, recent: Window, baseline: Window): number | null {
	const current = recent[key];
	const reference = baseline[key];
	return current === null || reference === null ? null : current - reference;
}

/** "Feb 2022", in UTC so the label doesn't depend on the viewer's time zone. */
export function formatMonth(timestamp: string): string {
	return new Date(timestamp).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
}

/** "5 Oct 2026", the date in a slide footer. */
export function formatDate(timestamp: string): string {
	return new Date(timestamp).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** "Sun 20 Sep, 19:39", in the viewer's time zone. */
export function formatMatchDate(timestamp: string): string {
	return new Date(timestamp).toLocaleString("en-GB", {
		weekday: "short",
		day: "numeric",
		month: "short",
		hour: "2-digit",
		minute: "2-digit",
	});
}

export function formatUpdated(timestamp: string): string {
	return new Date(timestamp).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}
