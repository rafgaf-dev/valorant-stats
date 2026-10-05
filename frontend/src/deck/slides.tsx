import type { PlayerSummary } from "../api";
import { actionItems, METRICS, metricComment, performanceRating, trendOf } from "../roast";
import { formatDelta, formatMetric, formatMonth, formatUpdated, metricDelta } from "../summary";
import { CalculationNotes } from "./CalculationNotes";
import { OutcomesChart } from "./OutcomesChart";

export type SlideContent = {
	title: string;
	wordArt?: boolean;
	body: React.ReactNode;
	notes: React.ReactNode;
};

/** The slides after the question, built from the summary. */
export function buildSlides(summary: PlayerSummary): SlideContent[] {
	const { player, windows } = summary;
	const { recent, sinceTracking } = windows;
	const sinceLabel = sinceTracking.since ? `Since ${formatMonth(sinceTracking.since)}` : "Since tracking";

	if (sinceTracking.matches === 0) {
		return [
			{
				title: `Performance review: ${player.displayName}`,
				body: (
					<div className="content-placeholder">
						<p className="placeholder-prompt">Click to add stats</p>
						<p>No completed competitive matches have been collected yet. Check back after his next game.</p>
					</div>
				),
				notes: <p>The collector hasn&apos;t found any completed competitive matches for this player yet.</p>,
			},
			closingSlide(summary),
		];
	}

	const rating = performanceRating(windows);
	return [
		{
			title: `Performance review: ${player.displayName}`,
			body: (
				<>
					<p className="slide-subtitle">
						Competitive, {player.region.toUpperCase()}. The last {recent.matches} matches compared with all{" "}
						{sinceTracking.matches}
						{sinceTracking.since ? ` since ${formatMonth(sinceTracking.since)}` : " tracked so far"}.
					</p>
					<div className="table-scroll">
						<table className="office-table">
							<thead>
								<tr>
									<th scope="col">Metric</th>
									<th scope="col">Last {recent.matches}</th>
									<th scope="col">{sinceLabel}</th>
									<th scope="col">Change</th>
									<th scope="col">Reviewer comment</th>
								</tr>
							</thead>
							<tbody>
								{METRICS.map(({ key, label }) => {
									const delta = metricDelta(key, recent, sinceTracking);
									return (
										<tr key={key}>
											<th scope="row">{label}</th>
											<td>{formatMetric(key, recent[key])}</td>
											<td>{formatMetric(key, sinceTracking[key])}</td>
											<td>{formatDelta(key, delta)}</td>
											<td>{metricComment(key, trendOf(delta))}</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</div>
					<p className="slide-note">
						Last {recent.matches}: {recent.kills} kills, {recent.deaths} deaths, {recent.assists} assists;{" "}
						{recent.headshots} head, {recent.bodyshots} body and {recent.legshots} leg hits.
					</p>
				</>
			),
			notes: <CalculationNotes />,
		},
		{
			title: `Match outcomes, last ${recent.matches}`,
			body: <OutcomesChart wins={recent.wins} losses={recent.losses} draws={recent.draws} />,
			notes: (
				<p>
					A 3D pie chart was chosen because it is the least readable chart type available, which felt
					appropriate.
				</p>
			),
		},
		{
			title: "Key takeaways",
			body: (
				<div className="takeaways">
					<p className="rating">
						Overall rating: <strong className={`rating-${rating.tone}`}>{rating.rating}</strong>
					</p>
					<p>{rating.summary}</p>
					<h3>Action items</h3>
					<ul className="office-bullets">
						{actionItems(player.displayName, player.agent).map((item) => (
							<li key={item}>{item}</li>
						))}
					</ul>
				</div>
			),
			notes: <p>The rating is always negative. That isn&apos;t a bug; it&apos;s the premise.</p>,
		},
		closingSlide(summary),
	];
}

function closingSlide(summary: PlayerSummary): SlideContent {
	return {
		title: "Questions?",
		wordArt: true,
		body: (
			<div className="closing">
				<p>Stats last updated {formatUpdated(summary.generatedAt)}.</p>
				<h3>Sources</h3>
				<p>
					Match data from the unofficial{" "}
					<a href="https://docs.henrikdev.xyz" rel="noreferrer">
						HenrikDev API
					</a>
					. Only completed competitive matches are counted.
				</p>
				<p className="legal">
					valorant-stats isn&apos;t endorsed by Riot Games and doesn&apos;t reflect the views or opinions of Riot
					Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all
					associated properties are trademarks or registered trademarks of Riot Games, Inc.
				</p>
			</div>
		),
		notes: <p>Do not take questions.</p>,
	};
}
