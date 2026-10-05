// The published summary contract (plan section 6). The collector writes it; the contract
// fixture in collector/tests/fixtures/summary.expected.json is tested on both sides.
// Version 2 added the detail counts and version 3 the recent matches; older summaries still
// render, without them.
export const SUPPORTED_SCHEMA_VERSIONS = [1, 2, 3] as const;

export type Window = {
	matches: number;
	wins: number;
	losses: number;
	draws: number;
	kills: number;
	deaths: number;
	assists: number;
	headshots: number;
	bodyshots: number;
	legshots: number;
	kd: number | null;
	winRate: number | null;
	headshotRate: number | null;
	// Schema 2: counted over matches with full details only (normally all of the recent ones).
	matchesWithDetails?: number;
	bottomFrags?: number;
	odinOrOperatorMains?: number;
};

export type MatchResult = "win" | "loss" | "draw";

/** One of the recent matches, newest first. Detail fields are null when they aren't known. */
export type RecentMatch = {
	playedAt: string;
	result: MatchResult;
	map: string | null;
	agent: string;
	kills: number;
	deaths: number;
	assists: number;
	bottomFragged: boolean | null;
	mainWeapon: string | null;
};

export type SinceTrackingWindow = Window & { since: string | null };

export type PlayerSummary = {
	schemaVersion: (typeof SUPPORTED_SCHEMA_VERSIONS)[number];
	player: { id: string; displayName: string; agent: string; region: string };
	queue: string;
	generatedAt: string;
	windows: { recent: Window; sinceTracking: SinceTrackingWindow };
	recentMatches?: RecentMatch[]; // schema 3
	lastImport: { status: "success" | "partial" | "failed"; finishedAt: string };
};

export type SummaryErrorKind = "not_found" | "unavailable" | "unsupported";

export class SummaryError extends Error {
	constructor(
		readonly kind: SummaryErrorKind,
		message: string,
	) {
		super(message);
		this.name = "SummaryError";
	}
}

export function summaryUrl(playerId: string): string {
	return `/data/players/${encodeURIComponent(playerId)}/summary.json`;
}

export async function getPlayerSummary(playerId: string, signal?: AbortSignal): Promise<PlayerSummary> {
	let response: Response;
	try {
		response = await fetch(summaryUrl(playerId), { signal });
	} catch (error) {
		if (error instanceof DOMException && error.name === "AbortError") throw error;
		throw new SummaryError("unavailable", "The stats couldn't be loaded.");
	}
	if (response.status === 404) {
		throw new SummaryError("not_found", "There are no stats for this player yet.");
	}
	if (!response.ok) {
		throw new SummaryError("unavailable", `The stats couldn't be loaded (HTTP ${response.status}).`);
	}

	let body: unknown;
	try {
		body = await response.json();
	} catch {
		throw new SummaryError("unavailable", "The stats file is damaged.");
	}
	const supported = (SUPPORTED_SCHEMA_VERSIONS as readonly unknown[]).includes(
		isRecord(body) ? body.schemaVersion : undefined,
	);
	if (!isRecord(body) || !supported || !isRecord(body.windows)) {
		throw new SummaryError("unsupported", "This page is out of date. Reload to get the latest version.");
	}
	return body as PlayerSummary;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

// Peer review votes, served by the votes function under /api (infrastructure/votes.tf).

export type VoteChoice = "fair" | "tooGenerous";

export type VoteTally = { fair: number; tooGenerous: number; yourVote: VoteChoice | null };

export type VoteResult = { tally: VoteTally; alreadyVoted: boolean };

export class VoteError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "VoteError";
	}
}

export function votesUrl(playerId: string): string {
	return `/api/votes/${encodeURIComponent(playerId)}`;
}

export async function getVotes(playerId: string, signal?: AbortSignal): Promise<VoteTally> {
	const response = await request(votesUrl(playerId), { signal });
	if (!response.ok) throw new VoteError(`The votes couldn't be loaded (HTTP ${response.status}).`);
	return parseTally(await readJson(response));
}

/** Casts a vote. One per viewer per day: a second one returns the first, unchanged. */
export async function castVote(playerId: string, choice: VoteChoice): Promise<VoteResult> {
	const body = JSON.stringify({ choice });
	const response = await request(votesUrl(playerId), {
		method: "POST",
		// CloudFront signs requests to the function URL, and can only sign a POST whose body
		// hash the browser supplies.
		headers: { "Content-Type": "application/json", "x-amz-content-sha256": await sha256Hex(body) },
		body,
	});
	if (response.ok || response.status === 409) {
		return { tally: parseTally(await readJson(response)), alreadyVoted: response.status === 409 };
	}
	throw new VoteError(`The vote couldn't be sent (HTTP ${response.status}).`);
}

async function request(url: string, init: RequestInit): Promise<Response> {
	try {
		return await fetch(url, init);
	} catch (error) {
		if (error instanceof DOMException && error.name === "AbortError") throw error;
		throw new VoteError("The votes couldn't be reached.");
	}
}

async function readJson(response: Response): Promise<unknown> {
	try {
		return await response.json();
	} catch {
		throw new VoteError("The votes response wasn't understood.");
	}
}

function parseTally(body: unknown): VoteTally {
	const valid =
		isRecord(body) &&
		Number.isInteger(body.fair) &&
		Number.isInteger(body.tooGenerous) &&
		(body.yourVote === null || body.yourVote === "fair" || body.yourVote === "tooGenerous");
	if (!valid) throw new VoteError("The votes response wasn't understood.");
	return { fair: body.fair as number, tooGenerous: body.tooGenerous as number, yourVote: body.yourVote as VoteChoice | null };
}

async function sha256Hex(text: string): Promise<string> {
	const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
	return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
