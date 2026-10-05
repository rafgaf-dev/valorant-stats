import { describe, expect, it } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary, Window } from "./api";
import { formatDate, formatDelta, formatMetric, formatMonth, isStale, metricDelta } from "./summary";

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
		expect(formatDelta("kd", null)).toBe("—");
	});

	it("formats the since-tracking month in UTC", () => {
		expect(formatMonth("2026-08-02T00:32:50Z")).toBe("Aug 2026");
		expect(formatMonth("2022-02-01T00:30:00Z")).toBe("Feb 2022");
	});

	it("formats the footer date", () => {
		expect(formatDate("2026-10-05T12:00:02Z")).toBe("5 Oct 2026");
	});

	it("has no delta when either side has no value", () => {
		expect(metricDelta("headshotRate", window({ headshotRate: null }), summary.windows.recent)).toBeNull();
	});
});
