import type { PlayerSummary, Window } from "./api";
import { metricDelta, type MetricKey } from "./summary";

export type Trend = "up" | "down" | "level" | "unknown";

export const METRICS: { key: MetricKey; label: string }[] = [
	{ key: "kd", label: "K/D" },
	{ key: "winRate", label: "Win rate" },
	{ key: "headshotRate", label: "Headshot %" },
];

export function trendOf(delta: number | null): Trend {
	if (delta === null) return "unknown";
	return delta > 0 ? "up" : delta < 0 ? "down" : "level";
}

export type Rating = { rating: string; summary: string };

/** An always-negative verdict, worded by how the recent numbers moved. */
export function performanceRating(windows: PlayerSummary["windows"]): Rating {
	const trends = METRICS.map(({ key }) => trendOf(metricDelta(key, windows.recent, windows.sinceTracking)));
	const known = trends.filter((trend) => trend !== "unknown");
	if (windows.recent.matches === 0 || known.length === 0) {
		return { rating: "Pending", summary: "Not enough recent games to judge. Suspicious in itself." };
	}
	const up = known.filter((trend) => trend === "up").length;
	const down = known.filter((trend) => trend === "down").length;
	if (up >= 2) {
		return { rating: "Needs improvement", summary: "The numbers went up. Somebody carried him." };
	}
	if (down >= 2) {
		return { rating: "Does not meet expectations", summary: "The numbers went down. Nobody is surprised." };
	}
	return { rating: "Inconsistent", summary: "Some numbers up, some down. Like his crosshair." };
}

/** The whole of the feedback, kept short on purpose. */
export function takeaways(recent: Window): string[] {
	const third =
		(recent.odinOrOperatorMains ?? 0) > 0
			? "Put the Odin down."
			: (recent.bottomFrags ?? 0) > 0
				? "Stop bottom fragging."
				: "Touch grass.";
	return ["Do better.", "Lock in.", third];
}
