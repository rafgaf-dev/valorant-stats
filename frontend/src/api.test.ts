import { describe, expect, it, vi } from "vitest";
import contract from "../../collector/tests/fixtures/summary.expected.json";
import { getPlayerSummary, SummaryError, summaryUrl } from "./api";

function stubFetch(response: Response | Error) {
	const fetchMock =
		response instanceof Error ? vi.fn().mockRejectedValue(response) : vi.fn().mockResolvedValue(response);
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

function json(body: unknown, status = 200) {
	return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

async function failure(playerId = "neon-main"): Promise<SummaryError> {
	const error = await getPlayerSummary(playerId).catch((caught: unknown) => caught);
	expect(error).toBeInstanceOf(SummaryError);
	return error as SummaryError;
}

describe("getPlayerSummary", () => {
	it("fetches the static summary path for the player", async () => {
		const fetchMock = stubFetch(json(contract));

		await expect(getPlayerSummary("neon-main")).resolves.toEqual(contract);
		expect(fetchMock).toHaveBeenCalledWith("/data/players/neon-main/summary.json", { signal: undefined });
	});

	it("encodes the player id in the path", () => {
		expect(summaryUrl("../secret")).toBe("/data/players/..%2Fsecret/summary.json");
	});

	it("reports a missing summary as not found", async () => {
		stubFetch(json({ error: "not_found" }, 404));

		expect((await failure()).kind).toBe("not_found");
	});

	it("reports server errors as unavailable", async () => {
		stubFetch(json({}, 503));

		const error = await failure();
		expect(error.kind).toBe("unavailable");
		expect(error.message).toContain("HTTP 503");
	});

	it("reports network failures as unavailable", async () => {
		stubFetch(new TypeError("Failed to fetch"));

		expect((await failure()).kind).toBe("unavailable");
	});

	it("reports an unreadable body as unavailable", async () => {
		stubFetch(new Response("<html>", { status: 200 }));

		expect((await failure()).kind).toBe("unavailable");
	});

	it("rejects other schema versions as unsupported", async () => {
		stubFetch(json({ ...contract, schemaVersion: 2 }));

		expect((await failure()).kind).toBe("unsupported");
	});

	it("passes aborts through untouched", async () => {
		stubFetch(new DOMException("aborted", "AbortError"));

		await expect(getPlayerSummary("neon-main")).rejects.toMatchObject({ name: "AbortError" });
	});
});
