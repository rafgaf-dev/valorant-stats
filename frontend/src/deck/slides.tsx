import type { ReactNode } from "react";
import type { PlayerSummary } from "../api";
import { performanceRating, takeaways } from "../roast";
import { formatMonth, formatUpdated } from "../summary";
import { ComparisonBars } from "./ComparisonBars";
import { OutcomesChart } from "./OutcomesChart";
import { PeerReview } from "./PeerReview";
import { RecentForm } from "./RecentForm";
import { ShameTally } from "./ShameTally";
import { SpinningNeon } from "./SpinningNeon";

export type SlideContent = {
	title: string;
	wordArt?: boolean;
	body: ReactNode;
};

/** The slides after the question, built from the summary. */
export function buildSlides(summary: PlayerSummary): SlideContent[] {
	const { player, windows, recentMatches = [] } = summary;
	const { recent, sinceTracking } = windows;

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
			},
			closingSlide(summary),
		];
	}

	const baselineLabel = sinceTracking.since ? `Since ${formatMonth(sinceTracking.since)}` : "Since tracking";
	const known = recent.matchesWithDetails ?? 0;
	return [
		{
			title: `Performance review: ${player.displayName}`,
			body: (
				<div className="review">
					<SpinningNeon caption={performanceRating(windows).summary} />
					<div className="review-charts">
						<ComparisonBars recent={recent} baseline={sinceTracking} baselineLabel={baselineLabel} />
						{known > 0 && (
							<div className="tallies">
								<ShameTally
									label="bottom-fragged"
									count={recent.bottomFrags ?? 0}
									known={known}
									total={recent.matches}
									tone="loss"
								/>
								<ShameTally
									label="with an Odin or Operator as his main gun"
									count={recent.odinOrOperatorMains ?? 0}
									known={known}
									total={recent.matches}
									tone="warning"
								/>
							</div>
						)}
						<p className="slide-note">
							{baselineLabel}: {sinceTracking.matches} games.
						</p>
					</div>
				</div>
			),
		},
		...(recentMatches.length > 0
			? [
					{
						title: `Recent form, last ${recentMatches.length}`,
						body: <RecentForm matches={recentMatches} />,
					},
				]
			: []),
		{
			title: `Games thrown vs not thrown, last ${recent.matches}`,
			body: <OutcomesChart wins={recent.wins} losses={recent.losses} draws={recent.draws} />,
		},
		{
			title: "Key takeaways",
			body: (
				<ul className="takeaways">
					{takeaways(recent, recentMatches).map((line) => (
						<li key={line}>{line}</li>
					))}
				</ul>
			),
		},
		{
			title: "Peer review",
			body: <PeerReview playerId={player.id} />,
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
	};
}
