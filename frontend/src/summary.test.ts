import { describe, expect, it } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary, Window } from "./api";
import { formatDelta, formatMetric, formatMonth, getVerdict, isStale, metricDelta } from "./summary";

const summary = contract as PlayerSummary;

function window(overrides: Partial<Window>): Window {
	return { ...summary.windows.recent, ...overrides };
}

describe("isStale", () => {
	const generatedAt = "2026-10-05T12:00:00Z";

	it("is fresh within 24 hours", () => {
		expect(isStale(generatedAt, new Date("2026-10-06T12:00:00Z"))).toBe(false);
	});

	it("is stale after 24 hours", () => {
		expect(isStale(generatedAt, new Date("2026-10-06T12:00:01Z"))).toBe(true);
	});
});

describe("formatting", () => {
	it("formats K/D with two decimals and rates as percentages", () => {
		expect(formatMetric("kd", 1.482233502538071)).toBe("1.48");
		expect(formatMetric("winRate", 0.4666666666666667)).toBe("46.7%");
		expect(formatMetric("headshotRate", null)).toBe("—");
	});

	it("formats signed deltas in each metric's unit", () => {
		expect(formatDelta("kd", 0.0704)).toBe("+0.07");
		expect(formatDelta("winRate", -0.0333)).toBe("−3.3 pts");
		expect(formatDelta("kd", 0)).toBe("±0.00");
	});

	it("formats the since-tracking month in UTC", () => {
		expect(formatMonth("2026-08-02T00:32:50Z")).toBe("Aug 2026");
		expect(formatMonth("2022-02-01T00:30:00Z")).toBe("Feb 2022");
	});

	it("has no delta when either side has no value", () => {
		expect(metricDelta("headshotRate", window({ headshotRate: null }), summary.windows.recent)).toBeNull();
	});
});

describe("getVerdict", () => {
	const baseline = { ...summary.windows.sinceTracking, kd: 1, winRate: 0.5, headshotRate: 0.3 };

	it("is cooking when at least two metrics improved", () => {
		const recent = window({ kd: 1.2, winRate: 0.6, headshotRate: 0.2 });
		expect(getVerdict({ recent, sinceTracking: baseline })?.mood).toBe("cooking");
	});

	it("is trolling when at least two metrics got worse", () => {
		const recent = window({ kd: 0.8, winRate: 0.4, headshotRate: 0.35 });
		expect(getVerdict({ recent, sinceTracking: baseline })?.mood).toBe("trolling");
	});

	it("is chaos when the metrics disagree", () => {
		const recent = window({ kd: 1.2, winRate: 0.4, headshotRate: 0.3 });
		expect(getVerdict({ recent, sinceTracking: baseline })?.mood).toBe("chaos");
	});

	it("ignores metrics without data", () => {
		const recent = window({ kd: 1.2, winRate: 0.6, headshotRate: null });
		expect(getVerdict({ recent, sinceTracking: baseline })?.mood).toBe("cooking");
	});

	it("gives no verdict without recent matches", () => {
		const recent = window({ matches: 0, kd: null, winRate: null, headshotRate: null });
		expect(getVerdict({ recent, sinceTracking: baseline })).toBeNull();
	});

	it("rules on the contract fixture", () => {
		// Recent K/D and win rate are up, headshot rate is down: cooking.
		expect(getVerdict(summary.windows)?.title).toBe("HE'S COOKING");
	});
});
