import { describe, expect, it } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary, Window } from "./api";
import { performanceRating, takeaways, trendOf } from "./roast";

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

	it("works with summaries from before the detail counts existed", () => {
		const legacy = recent({});
		delete legacy.bottomFrags;
		delete legacy.odinOrOperatorMains;

		expect(takeaways(legacy)).toHaveLength(3);
	});
});
