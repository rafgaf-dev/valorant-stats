import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import sampleSummary from "../dev-data/players/neon-main/summary.json";
import App from "./App";

function stubFetch(status: number, body: unknown) {
	const fetchMock = vi.fn().mockResolvedValue(
		new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
	);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

describe("App", () => {
	it("loads the player summary from the static data path", async () => {
		const fetchMock = stubFetch(200, sampleSummary);

		render(<App />);

		expect(screen.getByText("Pulling the dossier...")).toBeInTheDocument();
		expect(await screen.findByRole("heading", { name: "The Neon Menace" })).toBeInTheDocument();
		expect(screen.getByText("HE'S COOKING")).toBeInTheDocument();
		expect(fetchMock).toHaveBeenCalledWith("/data/players/neon-main/summary.json");
	});

	it("shows the error state when the summary is missing", async () => {
		stubFetch(404, { error: "not_found" });

		render(<App />);

		expect(await screen.findByText("Signal lost.")).toBeInTheDocument();
		expect(screen.getByText("not_found")).toBeInTheDocument();
	});
});
