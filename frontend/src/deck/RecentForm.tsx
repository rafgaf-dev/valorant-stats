import { type ReactNode, useState } from "react";
import type { MatchResult, RecentMatch } from "../api";
import { currentStreak, streakVerdict } from "../roast";
import { formatMatchDate } from "../summary";

const RESULT_LETTERS: Record<MatchResult, string> = { win: "W", loss: "L", draw: "D" };
const RESULT_WORDS: Record<MatchResult, string> = { win: "Win", loss: "Loss", draw: "Draw" };

/** The current streak, then every recent game as a W/L/D strip; pick one to see how it went. */
export function RecentForm({ matches }: { matches: RecentMatch[] }) {
	// Newest first in the summary; the strip reads oldest to latest, like a timeline.
	const timeline = [...matches].reverse();
	const [selected, setSelected] = useState(timeline.length - 1);
	const streak = currentStreak(matches);
	if (!streak) return null;

	const verdict = streakVerdict(streak);
	const streakStart = timeline.length - streak.length;
	const match = timeline[selected];

	return (
		<div className="form">
			<div className={`streak streak-${streak.result}`}>
				<p className="streak-headline">{verdict.headline}</p>
				<p className="streak-remark">{verdict.remark}</p>
			</div>

			<div className="form-strip">
				<ol className="form-games" aria-label="Recent games, oldest first">
					{timeline.map((game, index) => (
						<li key={game.playedAt} className={index >= streakStart ? "in-streak" : undefined}>
							<button
								type="button"
								className={`form-game form-${game.result}`}
								aria-pressed={index === selected}
								aria-label={`${formatMatchDate(game.playedAt)}, ${game.map ?? "unknown map"}: ${RESULT_WORDS[game.result]}`}
								onClick={() => setSelected(index)}
							>
								{RESULT_LETTERS[game.result]}
							</button>
						</li>
					))}
				</ol>
				<p className="form-axis">
					<span aria-hidden="true">Oldest</span>
					<span>Select a game to see how it went.</span>
					<span aria-hidden="true">Latest</span>
				</p>
			</div>

			<table className="form-details">
				<caption>
					Game {selected + 1} of {timeline.length}: {RESULT_WORDS[match.result]}
				</caption>
				<tbody>
					<Row label="Played">{formatMatchDate(match.playedAt)}</Row>
					<Row label="Map">{match.map ?? "Unknown"}</Row>
					<Row label="Agent">{match.agent}</Row>
					<Row label="K / D / A">
						{match.kills} / {match.deaths} / {match.assists}
					</Row>
					<Row label="Main gun">{match.mainWeapon ?? "Unknown"}</Row>
					<Row label="Bottom-fragged">
						{match.bottomFragged === null ? "Unknown" : match.bottomFragged ? "Yes" : "No"}
					</Row>
				</tbody>
			</table>
		</div>
	);
}

function Row({ label, children }: { label: string; children: ReactNode }) {
	return (
		<tr>
			<th scope="row">{label}</th>
			<td>{children}</td>
		</tr>
	);
}
