import type { PlayerSummary, Window } from "./api";

export const STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export type MetricKey = "kd" | "winRate" | "headshotRate";
export type Mood = "cooking" | "trolling" | "chaos";

export function isStale(generatedAt: string, now: Date = new Date()): boolean {
	return now.getTime() - new Date(generatedAt).getTime() > STALE_AFTER_MS;
}

export function formatMetric(key: MetricKey, value: number | null): string {
	if (value === null) return "—";
	return key === "kd" ? value.toFixed(2) : `${(value * 100).toFixed(1)}%`;
}

/** Signed difference, in the metric's own unit: "+0.12" or "−3.4 pts". */
export function formatDelta(key: MetricKey, delta: number): string {
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

export function formatUpdated(timestamp: string): string {
	return new Date(timestamp).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

const VERDICTS: Record<Mood, { title: string; text: string }> = {
	cooking: { title: "HE'S COOKING", text: "Someone check the scoreboard. This is suspiciously competent." },
	trolling: { title: "HE'S TROLLING", text: "The plan remains unclear, but the deaths are very real." },
	chaos: { title: "HE'S COOKING SOMETHING", text: "The numbers refuse to form a coherent explanation." },
};

/** Compares the recent window with the long-term one; null when there's nothing to compare. */
export function getVerdict(windows: PlayerSummary["windows"]) {
	const keys: MetricKey[] = ["kd", "winRate", "headshotRate"];
	const deltas = keys
		.map((key) => metricDelta(key, windows.recent, windows.sinceTracking))
		.filter((delta): delta is number => delta !== null);
	if (windows.recent.matches === 0 || deltas.length === 0) return null;

	const better = deltas.filter((delta) => delta > 0).length;
	const worse = deltas.filter((delta) => delta < 0).length;
	const mood: Mood = better >= 2 ? "cooking" : worse >= 2 ? "trolling" : "chaos";
	return { mood, ...VERDICTS[mood] };
}
