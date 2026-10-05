import type { PlayerSummary } from "./api";
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

// The running joke: whatever the numbers do, the review finds a problem.
const COMMENTS: Record<MetricKey, Record<Trend, string>> = {
	kd: {
		up: "Up, which management attributes to the enemy team being AFK.",
		down: "Down. The enemy team thanks him for his contribution.",
		level: "Unchanged. Consistently mid.",
		unknown: "Not enough data, which is somehow also his fault.",
	},
	winRate: {
		up: "Up. His teammates have asked to stop carrying him.",
		down: "Down, exactly as forecast in last quarter's review.",
		level: "Flat, like his crosshair placement.",
		unknown: "Not enough data, which is somehow also his fault.",
	},
	headshotRate: {
		up: "Up. Even a stopped clock hits a head twice a day.",
		down: "Down. Crosshair placement remains at ankle height.",
		level: "Unchanged. Still aiming at ankles.",
		unknown: "Not enough data, which is somehow also his fault.",
	},
};

export function metricComment(key: MetricKey, trend: Trend): string {
	return COMMENTS[key][trend];
}

export type Rating = { rating: string; summary: string; tone: "bad" | "worse" };

/** An always-negative performance rating, worded by how the recent numbers moved. */
export function performanceRating(windows: PlayerSummary["windows"]): Rating {
	const trends = METRICS.map(({ key }) => trendOf(metricDelta(key, windows.recent, windows.sinceTracking)));
	const known = trends.filter((trend) => trend !== "unknown");
	if (windows.recent.matches === 0 || known.length === 0) {
		return {
			rating: "Pending",
			summary: "Not enough recent matches to judge. Suspicious in itself.",
			tone: "bad",
		};
	}
	const up = known.filter((trend) => trend === "up").length;
	const down = known.filter((trend) => trend === "down").length;
	if (up >= 2) {
		return {
			rating: "Needs improvement",
			summary: "The numbers went up. An investigation into who carried him is under way.",
			tone: "bad",
		};
	}
	if (down >= 2) {
		return {
			rating: "Does not meet expectations",
			summary: "The numbers went down. Nobody in the group chat was surprised.",
			tone: "worse",
		};
	}
	return {
		rating: "Inconsistent",
		summary: "Some numbers went up and some went down, much like his crosshair.",
		tone: "bad",
	};
}

export function actionItems(name: string, agent: string): string[] {
	return [
		`Schedule a one-to-one with ${name} to find out what he thinks ${agent}'s abilities do.`,
		"Carry over last quarter's goal: die less.",
		"Share this deck with the group chat for peer review.",
	];
}
