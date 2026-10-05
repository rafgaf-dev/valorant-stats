import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import emptySample from "../dev-data/players/empty/summary.json";
import devSample from "../dev-data/players/neon-main/summary.json";
import App from "./App";
import { CELEBRATE_MS, REDUCED_CELEBRATE_MS, REVEAL_MS } from "./deck/timing";

function stubFetch(...responses: [number, unknown][]) {
	const fetchMock = vi.fn();
	for (const [status, body] of responses) {
		fetchMock.mockResolvedValueOnce(
			new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
		);
	}
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

function stubReducedMotion(reduce: boolean) {
	vi.stubGlobal(
		"matchMedia",
		vi.fn().mockReturnValue({ matches: reduce, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
	);
}

async function answerNo(which: 0 | 1 = 1) {
	const buttons = await screen.findAllByRole("button", { name: "No" });
	fireEvent.click(buttons[which]);
	// Two steps: the reveal timer only starts once React has rendered the first phase change.
	await act(() => vi.advanceTimersByTimeAsync(CELEBRATE_MS));
	await act(() => vi.advanceTimersByTimeAsync(REVEAL_MS));
}

function currentSlide() {
	return screen.getByRole("region", { name: /^Slide \d+ of \d+/ });
}

describe("App", () => {
	beforeEach(() => {
		vi.useFakeTimers({ now: new Date("2026-10-05T13:00:00Z"), shouldAdvanceTime: true });
		stubReducedMotion(false);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it("asks the question first, with both answers being no", async () => {
		const fetchMock = stubFetch([200, contract]);

		render(<App />);

		expect(screen.getByText("Opening presentation…")).toBeInTheDocument();
		expect(
			await screen.findByRole("heading", { name: "Do you think The Neon Menace played well recently?" }),
		).toBeInTheDocument();
		expect(fetchMock).toHaveBeenCalledWith("/data/players/neon-main/summary.json", expect.anything());
		const answers = screen.getAllByRole("button", { name: "No" });
		expect(answers).toHaveLength(2);
		expect(answers[1]).toHaveClass("green");
		expect(screen.queryByRole("table")).not.toBeInTheDocument();
		expect(within(currentSlide()).getByText("Unofficial fan project. Not endorsed by Riot Games.")).toBeVisible();
	});

	it("celebrates the answer, then reveals the performance review", async () => {
		stubFetch([200, contract]);
		render(<App />);
		const buttons = await screen.findAllByRole("button", { name: "No" });

		fireEvent.click(buttons[0]);

		expect(screen.getByRole("img", { name: "Thumbs up" })).toBeInTheDocument();
		expect(screen.getByRole("status")).toHaveTextContent("Correct.");
		await act(() => vi.advanceTimersByTimeAsync(CELEBRATE_MS));
		expect(document.querySelector(".checkerboard")).toBeInTheDocument();
		await act(() => vi.advanceTimersByTimeAsync(REVEAL_MS));
		expect(document.querySelector(".checkerboard")).not.toBeInTheDocument();

		const slide = currentSlide();
		expect(slide).toHaveAccessibleName("Slide 2 of 5: Performance review: The Neon Menace");
		expect(slide).toHaveTextContent("Last 15: 1.48");
		expect(slide).toHaveTextContent("Since Aug 2026: 1.41");
		expect(slide).toHaveTextContent("+0.07");
		expect(slide).toHaveTextContent("Somebody carried him.");
		expect(slide).toHaveTextContent("Since Aug 2026: 20 games.");
		expect(within(slide).getByRole("heading", { level: 2 })).toHaveFocus();
	});

	it("starts the Neon spin only once the reveal has finished", async () => {
		stubFetch([200, contract]);
		render(<App />);
		fireEvent.click((await screen.findAllByRole("button", { name: "No" }))[1]);
		await act(() => vi.advanceTimersByTimeAsync(CELEBRATE_MS));

		expect(document.querySelector(".viewport")).not.toHaveClass("presenting");
		await act(() => vi.advanceTimersByTimeAsync(REVEAL_MS));
		expect(document.querySelector(".viewport")).toHaveClass("presenting");
	});

	it("tallies bottom frags and Odin or Operator games when the details are known", async () => {
		const recent = { ...contract.windows.recent, matchesWithDetails: 15, bottomFrags: 6, odinOrOperatorMains: 2 };
		stubFetch([200, { ...contract, schemaVersion: 2, windows: { ...contract.windows, recent } }]);
		render(<App />);
		await answerNo();

		const slide = currentSlide();
		expect(slide).toHaveTextContent("6 of 15 games bottom-fragged");
		expect(slide).toHaveTextContent("2 of 15 games with an Odin or Operator as his main gun");
		expect(slide.querySelectorAll(".cell-loss")).toHaveLength(6);
		expect(slide.querySelectorAll(".cell-warning")).toHaveLength(2);

		fireEvent.keyDown(window, { key: "ArrowRight" });
		fireEvent.keyDown(window, { key: "ArrowRight" });
		expect(currentSlide()).toHaveTextContent("Do better.Lock in.Put the Odin down.");
	});

	it("leaves the tallies out for summaries without detail counts", async () => {
		const recent: Record<string, unknown> = { ...contract.windows.recent };
		for (const key of ["matchesWithDetails", "bottomFrags", "odinOrOperatorMains"]) delete recent[key];
		stubFetch([200, { ...contract, schemaVersion: 1, windows: { ...contract.windows, recent } }]);
		render(<App />);
		await answerNo();

		expect(currentSlide()).not.toHaveTextContent("bottom-fragged");
	});

	it("skips the animation when reduced motion is requested", async () => {
		stubReducedMotion(true);
		stubFetch([200, contract]);
		render(<App />);
		fireEvent.click((await screen.findAllByRole("button", { name: "No" }))[1]);

		expect(document.querySelector(".celebration")).toHaveClass("still");
		await act(() => vi.advanceTimersByTimeAsync(REDUCED_CELEBRATE_MS));

		expect(document.querySelector(".checkerboard")).not.toBeInTheDocument();
		expect(currentSlide()).toHaveAccessibleName(/^Slide 2 of 5/);
	});

	it("walks through the deck with the keyboard and controls", async () => {
		stubFetch([200, contract]);
		render(<App />);
		await answerNo();

		fireEvent.keyDown(window, { key: "ArrowRight" });
		expect(currentSlide()).toHaveAccessibleName("Slide 3 of 5: Games thrown vs not thrown, last 15");
		expect(screen.getByRole("list", { name: "15 games" })).toHaveTextContent("Not thrown: 7 Thrown: 8");
		expect(currentSlide()).toHaveTextContent("Draws count as thrown.");

		fireEvent.click(screen.getByRole("button", { name: "Next" }));
		const takeaways = currentSlide();
		expect(takeaways).toHaveAccessibleName("Slide 4 of 5: Key takeaways");
		expect(within(takeaways).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
			"Do better.",
			"Lock in.",
			"Touch grass.",
		]);

		fireEvent.keyDown(window, { key: "End" });
		const closing = currentSlide();
		expect(closing).toHaveTextContent("isn't endorsed by Riot Games");
		expect(within(closing).getByRole("link", { name: "HenrikDev API" })).toHaveAttribute(
			"href",
			"https://docs.henrikdev.xyz",
		);

		expect(screen.queryByRole("button", { name: /speaker notes/i })).not.toBeInTheDocument();

		fireEvent.click(screen.getByRole("button", { name: "End show" }));
		fireEvent.click(screen.getByRole("button", { name: "End of slide show, click to exit." }));
		expect(currentSlide()).toHaveAccessibleName(/^Slide 2 of 5/);

		fireEvent.keyDown(window, { key: "ArrowLeft" });
		expect(screen.getAllByRole("button", { name: "No" })).toHaveLength(2);
	});

	it("shows a warning bar when the data is over a day old", async () => {
		vi.setSystemTime(new Date("2026-10-07T12:00:00Z"));
		stubFetch([200, contract]);

		render(<App />);

		expect(await screen.findByText("Security warning")).toBeInTheDocument();
		expect(screen.getByText(/may be out of date/)).toBeInTheDocument();
	});

	it("shows a placeholder before the first match is collected", async () => {
		stubFetch([200, emptySample]);
		render(<App />);

		await answerNo();

		expect(currentSlide()).toHaveTextContent("Click to add stats");
		expect(screen.queryByRole("table")).not.toBeInTheDocument();
	});

	it.each([
		[404, { error: "not_found" }, "The presentation hasn't been made yet."],
		[503, {}, "The presentation couldn't be opened."],
		[200, { ...contract, schemaVersion: 99 }, "This presentation needs a newer version of the page."],
	])("shows an error dialog for HTTP %i", async (status, body, title) => {
		stubFetch([status, body]);

		render(<App />);

		const dialog = await screen.findByRole("alertdialog");
		expect(dialog).toHaveAccessibleName(title);
	});

	it("retries from the error dialog", async () => {
		const fetchMock = stubFetch([503, {}], [200, contract]);
		render(<App />);

		fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

		expect(await screen.findAllByRole("button", { name: "No" })).toHaveLength(2);
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it("serves the contract summary as the default development sample", () => {
		expect(devSample).toEqual(contract);
	});
});
