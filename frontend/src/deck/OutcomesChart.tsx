const LAYERS = 14; // stacked copies of the disc, each a little lower, form its edge

/** Games thrown (losses and draws) against games not thrown (wins), as a 3D pie. */
export function OutcomesChart({ wins, losses, draws }: { wins: number; losses: number; draws: number }) {
	const thrown = losses + draws;
	const total = wins + thrown;
	const notThrownEnd = total ? (wins / total) * 100 : 0;
	const slices = `conic-gradient(var(--accent-3) 0 ${notThrownEnd}%, var(--accent-2) ${notThrownEnd}% 100%)`;

	return (
		<div className="outcomes">
			<div className="pie-3d" aria-hidden="true">
				{Array.from({ length: LAYERS }, (_, layer) => {
					const depth = LAYERS - 1 - layer; // the first layers render lowest, the last on top
					return (
						<div
							key={layer}
							className={depth === 0 ? "pie-layer pie-top" : "pie-layer"}
							style={{ background: slices, top: `${depth}%` }}
						/>
					);
				})}
			</div>
			<div>
				<ul className="chart-legend" aria-label={`${total} games`}>
					<li>
						<span className="swatch swatch-win" aria-hidden="true" /> Not thrown: {wins}
					</li>
					<li>
						<span className="swatch swatch-loss" aria-hidden="true" /> Thrown: {thrown}
					</li>
				</ul>
				{draws > 0 && <p className="chart-note">Draws count as thrown.</p>}
			</div>
		</div>
	);
}
