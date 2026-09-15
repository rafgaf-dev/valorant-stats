export type Metric = {
	recent: number;
	lifetime: number;
	recentSampleSize: number;
	lifetimeSampleSize: number;
};

export type KdaMetric = Metric & {
	recentKills: number;
	recentDeaths: number;
	recentAssists: number;
	lifetimeKills: number;
	lifetimeDeaths: number;
	lifetimeAssists: number;
};

export type PlayerSummary = {
	player: { id: string; displayName: string; agent: string };
	metrics: { kda: KdaMetric; winRate: Metric; headshotPercentage: Metric };
	lastUpdatedAt: string;
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function getPlayerSummary(playerId: string): Promise<PlayerSummary> {
	const response = await fetch(`${apiBaseUrl}/v1/players/${encodeURIComponent(playerId)}/summary`);
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.error ?? `Stats request failed (${response.status})`);
	}
	return response.json() as Promise<PlayerSummary>;
}
