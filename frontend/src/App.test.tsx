import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import emptySample from "../dev-data/players/empty/summary.json";
import devSample from "../dev-data/players/neon-main/summary.json";
import App from "./App";

function stubFetch(status: number, body: unknown) {
	const fetchMock = vi.fn().mockResolvedValue(
		new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

function card(name: string) {
	return screen.getByRole("article", { name });
}

describe("App", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("renders the contract summary", async () => {
		vi.useFakeTimers({ now: new Date("2026-10-05T13:00:00Z"), toFake: ["Date"] });
		const fetchMock = stubFetch(200, contract);

		render(<App />);

		expect(screen.getByText("Pulling the dossier...")).toBeInTheDocument();
		expect(await screen.findByRole("heading", { level: 1, name: "The Neon Menace" })).toBeInTheDocument();
		expect(fetchMock).toHaveBeenCalledWith("/data/players/neon-main/summary.json", expect.anything());
		expect(screen.getByText("HE'S COOKING")).toBeInTheDocument();
		expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
			"Last 15 vs since aug 2026 (20 matches)",
		);
		expect(screen.queryByRole("status")).not.toBeInTheDocument();

		const kd = within(card("K/D"));
		expect(kd.getByText("1.48", { selector: ".stat-main" })).toBeInTheDocument();
		expect(kd.getByText("Since Aug 2026").nextSibling).toHaveTextContent("1.41");
		expect(kd.getByText("+0.07")).toBeInTheDocument();
		expect(kd.getByText("K/D/A 292 / 197 / 74")).toBeInTheDocument();
		expect(within(card("Win rate")).getByText("W–L–D 7–7–1")).toBeInTheDocument();
		expect(within(card("Headshot %")).getByText("31.8%", { selector: ".stat-main" })).toBeInTheDocument();
	});

	it("shows a stale banner when the data is over a day old", async () => {
		vi.useFakeTimers({ now: new Date("2026-10-07T12:00:00Z"), toFake: ["Date"] });
		stubFetch(200, contract);

		render(<App />);

		expect(await screen.findByRole("status")).toHaveTextContent("may be out of date");
		expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
	});

	it("shows the empty state before the first match is collected", async () => {
		stubFetch(200, emptySample);

		render(<App />);

		expect(await screen.findByText("Awaiting first match.")).toBeInTheDocument();
		expect(screen.queryByRole("article")).not.toBeInTheDocument();
	});

	it.each([
		[404, { error: "not_found" }, "No dossier yet."],
		[503, {}, "Signal lost."],
		[200, { ...contract, schemaVersion: 99 }, "This page is out of date."],
	])("shows the error state for HTTP %i", async (status, body, title) => {
		stubFetch(status, body);

		render(<App />);

		expect(await screen.findByRole("alert")).toHaveTextContent(title);
	});

	it("always shows the Riot disclaimer and data credit", async () => {
		stubFetch(200, contract);

		render(<App />);

		const footer = screen.getByRole("contentinfo");
		expect(footer).toHaveTextContent("isn't endorsed by Riot Games");
		expect(within(footer).getByRole("link", { name: "HenrikDev API" })).toHaveAttribute(
			"href",
			"https://docs.henrikdev.xyz",
		);
	});

	it("serves the contract summary as the default development sample", () => {
		expect(devSample).toEqual(contract);
	});
});
