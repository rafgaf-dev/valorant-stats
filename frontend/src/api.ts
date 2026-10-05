// The published summary contract (plan section 6). The collector writes it; the contract
// fixture in collector/tests/fixtures/summary.expected.json is tested on both sides.
export const SCHEMA_VERSION = 1;

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
};

export type SinceTrackingWindow = Window & { since: string | null };

export type PlayerSummary = {
	schemaVersion: typeof SCHEMA_VERSION;
	player: { id: string; displayName: string; agent: string; region: string };
	queue: string;
	generatedAt: string;
	windows: { recent: Window; sinceTracking: SinceTrackingWindow };
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
	if (!isRecord(body) || body.schemaVersion !== SCHEMA_VERSION || !isRecord(body.windows)) {
		throw new SummaryError("unsupported", "This page is out of date. Reload to get the latest version.");
	}
	return body as PlayerSummary;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}
