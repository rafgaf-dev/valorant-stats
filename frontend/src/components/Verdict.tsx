import type { PlayerSummary } from "../api";
import { getVerdict } from "../summary";

export function Verdict({ windows }: { windows: PlayerSummary["windows"] }) {
	const verdict = getVerdict(windows);
	if (!verdict) return null;

	return (
		<section className={`verdict ${verdict.mood}`} aria-label="Verdict">
			<div>
				<span className="verdict-stamp">OFFICIAL FRIEND GROUP RULING</span>
				<strong>{verdict.title}</strong>
			</div>
			<p>{verdict.text}</p>
		</section>
	);
}
