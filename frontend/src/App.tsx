import { useEffect, useState } from "react";
import { getPlayerSummary, type PlayerSummary } from "./api";
import { PlayerHeader } from "./components/PlayerHeader";
import { RecentGames } from "./components/RecentGames";
import { StatCard } from "./components/StatCard";
import "./styles.css";

const PLAYER_ID = import.meta.env.VITE_PLAYER_ID ?? "neon-main";

function getVerdict(metrics: PlayerSummary["metrics"]) {

	const deltas = [
		metrics.kda.recent - metrics.kda.lifetime,
		metrics.winRate.recent - metrics.winRate.lifetime,
		metrics.headshotPercentage.recent - metrics.headshotPercentage.lifetime,
	];
	const good = deltas.filter((delta) => delta > 0).length;
	const bad = deltas.filter((delta) => delta < 0).length;

	if (good >= 2) {
		return { mood: "cooking", title: "HE'S COOKING", text: "Someone check the scoreboard. This is suspiciously competent." };
	}
	if (bad >= 2) {
		return { mood: "trolling", title: "HE'S TROLLING", text: "The plan remains unclear, but the deaths are very real." };
	}
	return { mood: "chaos", title: "HE'S COOKING SOMETHING", text: "The numbers refuse to form a coherent explanation." };
}

export default function App() {
	const [summary, setSummary] = useState<PlayerSummary | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		getPlayerSummary(PLAYER_ID).then(setSummary).catch((requestError: Error) => setError(requestError.message));
	}, []);

	return (
		<main className="app-shell">
			<div className="grain" aria-hidden="true" />
			<section className="dashboard" aria-live="polite">
				<div className="eyebrow">VALORANT // UNAUTHORIZED FRIEND ANALYSIS</div>
				{error ? (
					<div className="state-panel"><strong>Signal lost.</strong><span>{error}</span></div>
				) : summary ? (
					<>
						<PlayerHeader summary={summary} />
						{summary.metrics ? (
							<>
								<div className={`verdict ${getVerdict(summary.metrics).mood}`}>
									<div><span className="verdict-stamp">OFFICIAL FRIEND GROUP RULING</span><strong>{getVerdict(summary.metrics).title}</strong></div>
									<p>{getVerdict(summary.metrics).text}</p>
								</div>
								<div className="section-heading"><span>Receipts</span><span>LAST 15 VS CAREER DAMAGE</span></div>
								<div className="stats-grid">
									<StatCard label="K / D / A" metric={summary.metrics.kda} kind="kda" />
									<StatCard label="Win rate" metric={summary.metrics.winRate} kind="percentage" />
									<StatCard label="Headshot %" metric={summary.metrics.headshotPercentage} kind="percentage" />
								</div>
								<RecentGames />
							</>
						) : <div className="state-panel"><strong>Awaiting first import.</strong><span>The collector has not published a competitive match snapshot yet.</span></div>}
					</>
				) : (
					<div className="state-panel loading"><strong>Pulling the dossier...</strong><span>Connecting to the cached match archive.</span></div>
				)}
				<footer>Unofficial fan project. VALORANT and all related imagery are property of Riot Games.</footer>
			</section>
		</main>
	);
}
