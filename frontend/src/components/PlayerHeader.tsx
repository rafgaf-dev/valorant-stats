import type { PlayerSummary } from "../api";
import neonPortrait from "../assets/neon-portrait.webp";
import { formatUpdated } from "../summary";

const AGENT_ART: Record<string, string> = { Neon: neonPortrait };

export function PlayerHeader({ summary }: { summary: PlayerSummary }) {
	const { player, queue, generatedAt } = summary;
	const art = AGENT_ART[player.agent];

	return (
		<header className="player-header">
			<div className="agent-art">
				{art && <img src={art} alt={`${player.agent}, the player's main agent`} width={640} height={782} />}
				<span>AGENT // {player.agent.toUpperCase()}</span>
			</div>
			<div className="player-copy">
				<p className="kicker">BREAKING NEWS FROM THE QUEUE</p>
				<h1>{player.displayName}</h1>
				<p className="dek">
					Professional {player.agent} player. Amateur decision-maker. The stats have been subpoenaed.
				</p>
				<ul className="metadata" aria-label="Data details">
					<li>{player.region.toUpperCase()}</li>
					<li>{queue.toUpperCase()} ONLY</li>
					<li>
						UPDATED <time dateTime={generatedAt}>{formatUpdated(generatedAt)}</time>
					</li>
				</ul>
			</div>
		</header>
	);
}
