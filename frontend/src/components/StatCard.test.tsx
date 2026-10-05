import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import contract from "../../../collector/tests/fixtures/summary.expected.json";
import type { PlayerSummary } from "../api";
import { StatCard } from "./StatCard";

const { recent, sinceTracking } = (contract as PlayerSummary).windows;

function renderCard(recentOverrides: Partial<typeof recent>) {
	render(
		<StatCard
			label="Headshot %"
			metric="headshotRate"
			recent={{ ...recent, ...recentOverrides }}
			baseline={sinceTracking}
			baselineLabel="Since Aug 2026"
			detail="detail"
		/>,
	);
}

describe("StatCard", () => {
	it("labels the trend in words, not just colour", () => {
		renderCard({ headshotRate: 0.2 });

		expect(screen.getByText("trolling")).toBeInTheDocument();
		expect(screen.getByText("−12.3 pts")).toBeInTheDocument();
	});

	it("says when there isn't enough data", () => {
		renderCard({ headshotRate: null });

		expect(screen.getByText("Not enough data")).toBeInTheDocument();
		expect(screen.queryByText("trolling")).not.toBeInTheDocument();
	});
});
