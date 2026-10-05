import { useCallback, useEffect, useState } from "react";
import { getPlayerSummary, SummaryError, type PlayerSummary } from "./api";
import { Deck } from "./deck/Deck";
import { playerIdFromLocation } from "./player";
import { formatUpdated, isStale } from "./summary";

type State =
	| { status: "loading" }
	| { status: "error"; error: SummaryError }
	| { status: "loaded"; summary: PlayerSummary };

const ERROR_TITLES: Record<SummaryError["kind"], string> = {
	not_found: "The presentation hasn't been made yet.",
	unavailable: "The presentation couldn't be opened.",
	unsupported: "This presentation needs a newer version of the page.",
};

export default function App() {
	const [state, setState] = useState<State>({ status: "loading" });
	const [attempt, setAttempt] = useState(0);
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
	}, [playerId, attempt]);

	const retry = useCallback(() => {
		setState({ status: "loading" });
		setAttempt((count) => count + 1);
	}, []);

	return (
		<main className="stage">
			{state.status === "loading" && (
				<div className="loading" role="status">
					<p>Opening presentation…</p>
					<div className="progress" aria-hidden="true">
						<span />
					</div>
				</div>
			)}
			{state.status === "error" && (
				<div className="dialog" role="alertdialog" aria-labelledby="dialog-title" aria-describedby="dialog-message">
					<p className="dialog-titlebar">Presentation</p>
					<div className="dialog-body">
						<h1 id="dialog-title">{ERROR_TITLES[state.error.kind]}</h1>
						<p id="dialog-message">{state.error.message}</p>
						<button type="button" className="office-button" onClick={retry} autoFocus>
							Try again
						</button>
					</div>
				</div>
			)}
			{state.status === "loaded" && (
				<>
					<h1 className="visually-hidden">
						{state.summary.player.displayName}&apos;s Valorant performance review
					</h1>
					{isStale(state.summary.generatedAt) && (
						<p className="message-bar" role="status">
							<b>Security warning</b> These stats were last updated {formatUpdated(state.summary.generatedAt)} and
							may be out of date.
						</p>
					)}
					<Deck summary={state.summary} />
				</>
			)}
		</main>
	);
}
