import { describe, expect, it } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary, RecentMatch, Window } from "./api";
import { currentStreak, performanceRating, streakVerdict, takeaways, trendOf } from "./roast";

const summary = contract as PlayerSummary;
const baseline = { ...summary.windows.sinceTracking, kd: 1, winRate: 0.5, headshotRate: 0.3 };

function games(results: string): RecentMatch[] {
	const letters: Record<string, RecentMatch["result"]> = { W: "win", L: "loss", D: "draw" };
	return [...results].map((letter) => ({ ...summary.recentMatches![0], result: letters[letter] }));
}

function recent(overrides: Partial<Window>): Window {
	return { ...summary.windows.recent, ...overrides };
}

describe("performanceRating", () => {
	it("still finds fault when the numbers improve", () => {
		const rating = performanceRating({
			recent: recent({ kd: 1.2, winRate: 0.6, headshotRate: 0.2 }),
			sinceTracking: baseline,
		});

		expect(rating).toEqual({ rating: "Needs improvement", summary: "The numbers went up. Somebody carried him." });
	});

	it("is harshest when the numbers get worse", () => {
		const rating = performanceRating({
			recent: recent({ kd: 0.8, winRate: 0.4, headshotRate: 0.35 }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Does not meet expectations");
	});

	it("calls mixed numbers inconsistent", () => {
		const rating = performanceRating({
			recent: recent({ kd: 1.2, winRate: 0.4, headshotRate: 0.3 }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Inconsistent");
	});

	it("is pending without recent matches", () => {
		const rating = performanceRating({
			recent: recent({ matches: 0, kd: null, winRate: null, headshotRate: null }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Pending");
	});

	it("maps deltas to trends", () => {
		expect([trendOf(0.1), trendOf(-0.1), trendOf(0), trendOf(null)]).toEqual(["up", "down", "level", "unknown"]);
	});
});

describe("takeaways", () => {
	it("keeps it short", () => {
		expect(takeaways(recent({ bottomFrags: 0, odinOrOperatorMains: 0 }))).toEqual([
			"Do better.",
			"Lock in.",
			"Touch grass.",
		]);
	});

	it("calls out the Odin first", () => {
		expect(takeaways(recent({ bottomFrags: 4, odinOrOperatorMains: 1 }))[2]).toBe("Put the Odin down.");
	});

	it("calls out bottom fragging next", () => {
		expect(takeaways(recent({ bottomFrags: 4, odinOrOperatorMains: 0 }))[2]).toBe("Stop bottom fragging.");
	});

	it("adds a line for a loss streak of three or more", () => {
		const window = recent({ bottomFrags: 0, odinOrOperatorMains: 0 });

		expect(takeaways(window, games("LLLW"))).toContain("End the loss streak.");
		expect(takeaways(window, games("LLWL"))).toHaveLength(3);
		expect(takeaways(window, games("WLLL"))).toHaveLength(3);
	});

	it("works with summaries from before the detail counts existed", () => {
		const legacy = recent({});
		delete legacy.bottomFrags;
		delete legacy.odinOrOperatorMains;

		expect(takeaways(legacy)).toHaveLength(3);
	});
});

describe("currentStreak", () => {
	it("counts identical results back from the newest game", () => {
		expect(currentStreak(games("LLLWL"))).toEqual({ result: "loss", length: 3 });
		expect(currentStreak(games("WWWW"))).toEqual({ result: "win", length: 4 });
		expect(currentStreak(games("DW"))).toEqual({ result: "draw", length: 1 });
		expect(currentStreak([])).toBeNull();
	});

	it("never gives him credit", () => {
		expect(streakVerdict({ result: "loss", length: 5 })).toEqual({
			headline: "5 losses in a row",
			remark: "Somebody check on him.",
		});
		expect(streakVerdict({ result: "win", length: 3 }).remark).toBe("Carried, presumably.");
		expect(streakVerdict({ result: "win", length: 1 })).toEqual({
			headline: "Won the last one",
			remark: "Don't get used to it.",
		});
	});
});
