type Props = {
	label: string;
	count: number;
	/** Matches the count was measured over (those with full details). */
	known: number;
	/** All matches in the window; any beyond `known` show as unknown. */
	total: number;
	tone: "loss" | "warning";
};

// One square per game, filled for each game that counts against him.
export function ShameTally({ label, count, known, total, tone }: Props) {
	return (
		<div className="tally">
			<p className="tally-label">
				<strong>{count}</strong> of {known} games {label}
			</p>
			<div className="tally-cells" aria-hidden="true">
				{Array.from({ length: total }, (_, index) => (
					<span
						key={index}
						className={index < count ? `cell cell-${tone}` : index < known ? "cell" : "cell cell-unknown"}
					/>
				))}
			</div>
		</div>
	);
}
