export function OutcomesChart({ wins, losses, draws }: { wins: number; losses: number; draws: number }) {
	const total = wins + losses + draws;
	const winEnd = (wins / total) * 100;
	const lossEnd = winEnd + (losses / total) * 100;
	const slices = `conic-gradient(var(--accent-3) 0 ${winEnd}%, var(--accent-2) ${winEnd}% ${lossEnd}%, var(--draw) ${lossEnd}% 100%)`;
	const legend = [
		{ label: "Wins", value: wins, className: "swatch-win" },
		{ label: "Losses", value: losses, className: "swatch-loss" },
		{ label: "Draws", value: draws, className: "swatch-draw" },
	];

	return (
		<div className="outcomes">
			<div className="pie-3d" aria-hidden="true">
				<div className="pie-side" style={{ background: slices }} />
				<div className="pie-top" style={{ background: slices }} />
			</div>
			<ul className="chart-legend" aria-label={`${total} matches`}>
				{legend.map(({ label, value, className }) => (
					<li key={label}>
						<span className={`swatch ${className}`} aria-hidden="true" /> {label}: {value}
					</li>
				))}
			</ul>
		</div>
	);
}
