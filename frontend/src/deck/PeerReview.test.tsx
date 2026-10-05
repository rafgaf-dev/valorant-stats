import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PeerReview } from "./PeerReview";

function json(status: number, body: unknown) {
	return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function stubFetch(...responses: (Response | Error)[]) {
	const fetchMock = vi.fn();
	for (const response of responses) {
		if (response instanceof Error) fetchMock.mockRejectedValueOnce(response);
		else fetchMock.mockResolvedValueOnce(response);
	}
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

const NO_VOTE = { fair: 2, tooGenerous: 5, yourVote: null };

describe("PeerReview", () => {
	it("asks first, then shows the results after a vote", async () => {
		const fetchMock = stubFetch(json(200, NO_VOTE), json(200, { fair: 3, tooGenerous: 5, yourVote: "fair" }));
		render(<PeerReview playerId="neon-main" />);

		expect(screen.getByText("Was this review fair?")).toBeInTheDocument();
		fireEvent.click(screen.getByRole("button", { name: "Fair" }));

		expect(await screen.findByRole("figure")).toHaveTextContent("Results so far: 8 votes");
		expect(screen.getByRole("status")).toHaveTextContent("noted and will be ignored");
		expect(screen.getByRole("figure")).toHaveTextContent("Fair3 (38%)");
		expect(screen.getByRole("figure")).toHaveTextContent("Too generous5 (63%)");
		expect(screen.queryByRole("button", { name: "Fair" })).not.toBeInTheDocument();
		expect(document.activeElement).toHaveClass("vote-results");

		const [url, init] = fetchMock.mock.calls[1];
		const body = '{"choice":"fair"}';
		expect(url).toBe("/api/votes/neon-main");
		expect(init).toMatchObject({ method: "POST", body });
		// sha256sum of the body, which CloudFront needs to sign the request
		expect(init.headers["x-amz-content-sha256"]).toBe("76b79da5bdd54e8707e711ce58e30dc38e222ae1d90932fb3604c222ab64ae02");
	});

	it("opens on the results when this viewer already voted today", async () => {
		stubFetch(json(200, { fair: 1, tooGenerous: 0, yourVote: "tooGenerous" }));
		render(<PeerReview playerId="neon-main" />);

		expect(await screen.findByRole("figure")).toHaveTextContent("Results so far: 1 vote");
		expect(screen.getByRole("status")).toHaveTextContent("You already voted today: Too generous.");
		expect(screen.queryByRole("button")).not.toBeInTheDocument();
	});

	it("shows the earlier vote when the server already has one", async () => {
		stubFetch(json(200, NO_VOTE), json(409, { error: "already_voted", fair: 2, tooGenerous: 5, yourVote: "fair" }));
		render(<PeerReview playerId="neon-main" />);

		fireEvent.click(screen.getByRole("button", { name: "Too generous" }));

		expect(await screen.findByRole("figure")).toBeInTheDocument();
		expect(screen.getByRole("status")).toHaveTextContent("You already voted today: Fair.");
	});

	it("keeps the buttons when the vote can't be sent", async () => {
		stubFetch(new TypeError("offline"), json(403, { message: "Forbidden" }));
		render(<PeerReview playerId="neon-main" />);

		fireEvent.click(screen.getByRole("button", { name: "Fair" }));

		expect(await screen.findByText("Your vote couldn't be sent. Try again later.")).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "Fair" })).toBeEnabled();
		expect(screen.queryByRole("figure")).not.toBeInTheDocument();
	});
});
