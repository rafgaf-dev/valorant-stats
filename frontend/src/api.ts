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

export async function getPlayerSummary(playerId: string): Promise<PlayerSummary> {
	const response = await fetch(`/data/players/${encodeURIComponent(playerId)}/summary.json`);
	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.error ?? `Stats request failed (${response.status})`);
	}
	return response.json() as Promise<PlayerSummary>;
}
