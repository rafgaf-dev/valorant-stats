import type { PlayerSummary } from "../api";

export function PlayerHeader({ summary }: { summary: PlayerSummary }) {
	const imageUrl = import.meta.env.VITE_NEON_IMAGE_URL ?? "https://media.valorant-api.com/agents/bb2a4828-46eb-8cd1-e765-15848195d751/fullportrait.png";
	const updated = new Date(summary.lastUpdatedAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

	return (
		<header className="player-header">
			<div className="agent-art"><img src={imageUrl} alt="Neon" /><span>AGENT // NEON</span></div>
			<div className="player-copy">
				<p className="kicker">BREAKING NEWS FROM THE QUEUE</p>
				<h1>{summary.player.displayName}</h1>
				<p className="dek">Professional Neon player. Amateur decision-maker. The stats have been subpoenaed.</p>
				<div className="metadata"><span>EUROPE</span><span>COMPETITIVE ONLY</span><span>LAST SEEN {updated}</span></div>
			</div>
		</header>
	);
}
