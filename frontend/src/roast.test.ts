import { describe, expect, it } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary, Window } from "./api";
import { actionItems, metricComment, performanceRating, trendOf } from "./roast";

const summary = contract as PlayerSummary;
const baseline = { ...summary.windows.sinceTracking, kd: 1, winRate: 0.5, headshotRate: 0.3 };

function recent(overrides: Partial<Window>): Window {
	return { ...summary.windows.recent, ...overrides };
}

describe("performanceRating", () => {
	it("still finds fault when the numbers improve", () => {
		const rating = performanceRating({
			recent: recent({ kd: 1.2, winRate: 0.6, headshotRate: 0.2 }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Needs improvement");
		expect(rating.summary).toContain("who carried him");
	});

	it("is harshest when the numbers get worse", () => {
		const rating = performanceRating({
			recent: recent({ kd: 0.8, winRate: 0.4, headshotRate: 0.35 }),
			sinceTracking: baseline,
		});

		expect(rating).toMatchObject({ rating: "Does not meet expectations", tone: "worse" });
	});

	it("calls mixed numbers inconsistent", () => {
		const rating = performanceRating({
			recent: recent({ kd: 1.2, winRate: 0.4, headshotRate: 0.3 }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Inconsistent");
	});

	it("ignores metrics without data", () => {
		const rating = performanceRating({
			recent: recent({ kd: 1.2, winRate: 0.6, headshotRate: null }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Needs improvement");
	});

	it("is pending without recent matches", () => {
		const rating = performanceRating({
			recent: recent({ matches: 0, kd: null, winRate: null, headshotRate: null }),
			sinceTracking: baseline,
		});

		expect(rating.rating).toBe("Pending");
	});

	it("is never positive on the contract fixture", () => {
		// K/D and win rate are up, headshot rate is down: improvement, which is suspicious.
		expect(performanceRating(summary.windows).rating).toBe("Needs improvement");
	});
});

describe("comments", () => {
	it("maps deltas to trends", () => {
		expect([trendOf(0.1), trendOf(-0.1), trendOf(0), trendOf(null)]).toEqual(["up", "down", "level", "unknown"]);
	});

	it("roasts every metric in every direction", () => {
		for (const key of ["kd", "winRate", "headshotRate"] as const) {
			for (const trend of ["up", "down", "level", "unknown"] as const) {
				expect(metricComment(key, trend)).toMatch(/\.$/);
			}
		}
		expect(metricComment("headshotRate", "down")).toContain("ankle");
	});

	it("names the player and agent in the action items", () => {
		expect(actionItems("Alex", "Neon")[0]).toBe(
			"Schedule a one-to-one with Alex to find out what he thinks Neon's abilities do.",
		);
	});
});
