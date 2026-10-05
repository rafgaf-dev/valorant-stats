import { useEffect, useState } from "react";
import { getPlayerSummary, SummaryError, type PlayerSummary } from "./api";
import { MetricNotes } from "./components/MetricNotes";
import { PlayerHeader } from "./components/PlayerHeader";
import { StatCard } from "./components/StatCard";
import { Verdict } from "./components/Verdict";
import { playerIdFromLocation } from "./player";
import { formatMonth, formatUpdated, isStale } from "./summary";

type State =
	| { status: "loading" }
	| { status: "error"; error: SummaryError }
	| { status: "loaded"; summary: PlayerSummary };

const ERROR_TITLES: Record<SummaryError["kind"], string> = {
	not_found: "No dossier yet.",
	unavailable: "Signal lost.",
	unsupported: "This page is out of date.",
};

export default function App() {
	const [state, setState] = useState<State>({ status: "loading" });
	const playerId = playerIdFromLocation(window.location.search, import.meta.env.DEV);

	useEffect(() => {
		const controller = new AbortController();
		getPlayerSummary(playerId, controller.signal)
			.then((summary) => setState({ status: "loaded", summary }))
			.catch((error: unknown) => {
				if (controller.signal.aborted) return;
				const failure =
					error instanceof SummaryError ? error : new SummaryError("unavailable", "The stats couldn't be loaded.");
				setState({ status: "error", error: failure });
			});
		return () => controller.abort();
	}, [playerId]);

	return (
		<main className="app-shell">
			<div className="grain" aria-hidden="true" />
			<div className="dashboard" aria-live="polite" aria-busy={state.status === "loading"}>
				<p className="eyebrow">VALORANT // UNAUTHORIZED FRIEND ANALYSIS</p>
				{state.status === "loading" && (
					<div className="state-panel loading">
						<strong>Pulling the dossier...</strong>
						<span>Connecting to the cached match archive.</span>
					</div>
				)}
				{state.status === "error" && (
					<div className="state-panel" role="alert">
						<strong>{ERROR_TITLES[state.error.kind]}</strong>
						<span>{state.error.message}</span>
					</div>
				)}
				{state.status === "loaded" && <Dashboard summary={state.summary} />}
				<footer>
					<p>
						valorant-stats isn&apos;t endorsed by Riot Games and doesn&apos;t reflect the views or opinions of Riot
						Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all
						associated properties are trademarks or registered trademarks of Riot Games, Inc.
					</p>
					<p>
						Match data from the unofficial{" "}
						<a href="https://docs.henrikdev.xyz" rel="noreferrer">
							HenrikDev API
						</a>
						.
					</p>
				</footer>
			</div>
		</main>
	);
}

function Dashboard({ summary }: { summary: PlayerSummary }) {
	const { recent, sinceTracking } = summary.windows;

	if (sinceTracking.matches === 0) {
		return (
			<>
				<PlayerHeader summary={summary} />
				<div className="state-panel">
					<strong>Awaiting first match.</strong>
					<span>No completed competitive matches have been collected yet.</span>
				</div>
			</>
		);
	}

	const sinceLabel = sinceTracking.since ? `Since ${formatMonth(sinceTracking.since)}` : "Since tracking";
	return (
		<>
			{isStale(summary.generatedAt) && (
				<p className="stale-banner" role="status">
					These stats were last updated {formatUpdated(summary.generatedAt)} and may be out of date.
				</p>
			)}
			<PlayerHeader summary={summary} />
			<Verdict windows={summary.windows} />
			<h2 className="section-heading">
				<span>Receipts</span>
				<span>
					Last {recent.matches} vs {sinceLabel.toLowerCase()} ({sinceTracking.matches} matches)
				</span>
			</h2>
			<div className="stats-grid">
				<StatCard
					label="K/D"
					metric="kd"
					recent={recent}
					baseline={sinceTracking}
					baselineLabel={sinceLabel}
					detail={`K/D/A ${recent.kills} / ${recent.deaths} / ${recent.assists}`}
				/>
				<StatCard
					label="Win rate"
					metric="winRate"
					recent={recent}
					baseline={sinceTracking}
					baselineLabel={sinceLabel}
					detail={`W–L–D ${recent.wins}–${recent.losses}–${recent.draws}`}
				/>
				<StatCard
					label="Headshot %"
					metric="headshotRate"
					recent={recent}
					baseline={sinceTracking}
					baselineLabel={sinceLabel}
					detail={`Hits: ${recent.headshots} head · ${recent.bodyshots} body · ${recent.legshots} leg`}
				/>
			</div>
			<MetricNotes />
		</>
	);
}
