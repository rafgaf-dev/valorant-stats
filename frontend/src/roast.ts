import type { MatchResult, PlayerSummary, RecentMatch, Window } from "./api";
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

export type Streak = { result: MatchResult; length: number };

/** The run of identical results ending with the newest match (matches are newest first). */
export function currentStreak(matches: RecentMatch[]): Streak | null {
	if (matches.length === 0) return null;
	const result = matches[0].result;
	const length = matches.findIndex((match) => match.result !== result);
	return { result, length: length === -1 ? matches.length : length };
}

const PLURALS: Record<MatchResult, string> = { win: "wins", loss: "losses", draw: "draws" };

/** "5 losses in a row", with a remark that never gives him credit. */
export function streakVerdict({ result, length }: Streak): { headline: string; remark: string } {
	if (length === 1) {
		const headline = { win: "Won the last one", loss: "Lost the last one", draw: "Drew the last one" }[result];
		const remark = {
			win: "Don't get used to it.",
			loss: "A streak has to start somewhere.",
			draw: "Not a win, though.",
		}[result];
		return { headline, remark };
	}
	const remark = { win: "Carried, presumably.", loss: "Somebody check on him.", draw: "Somehow." }[result];
	return { headline: `${length} ${PLURALS[result]} in a row`, remark };
}

export const LOSS_STREAK_CALLOUT = 3;

/** The whole of the feedback, kept short on purpose. */
export function takeaways(recent: Window, recentMatches: RecentMatch[] = []): string[] {
	const third =
		(recent.odinOrOperatorMains ?? 0) > 0
			? "Put the Odin down."
			: (recent.bottomFrags ?? 0) > 0
				? "Stop bottom fragging."
				: "Touch grass.";
	const streak = currentStreak(recentMatches);
	const onALossStreak = streak?.result === "loss" && streak.length >= LOSS_STREAK_CALLOUT;
	return ["Do better.", "Lock in.", third, ...(onALossStreak ? ["End the loss streak."] : [])];
}
