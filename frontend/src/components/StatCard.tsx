import type { ReactNode } from "react";
import type { Window } from "../api";
import { formatDelta, formatMetric, metricDelta, type MetricKey } from "../summary";

type Props = {
	label: string;
	metric: MetricKey;
	recent: Window;
	baseline: Window;
	baselineLabel: string;
	detail: ReactNode;
};

export function StatCard({ label, metric, recent, baseline, baselineLabel, detail }: Props) {
	const delta = metricDelta(metric, recent, baseline);
	const trend = delta === null ? null : delta > 0 ? "up" : delta < 0 ? "down" : "level";
	const commentary = { up: "cooking", down: "trolling", level: "unchanged, somehow" };

	return (
		<article className="stat-card" aria-labelledby={`stat-${metric}`}>
			<div className="stat-label">
				<h3 id={`stat-${metric}`}>{label}</h3>
				{trend && delta !== null && (
					<span className={`delta ${trend}`}>
						{commentary[trend]} <span className="delta-value">{formatDelta(metric, delta)}</span>
					</span>
				)}
			</div>
			{recent[metric] === null ? (
				<p className="stat-main empty">Not enough data</p>
			) : (
				<p className="stat-main">{formatMetric(metric, recent[metric])}</p>
			)}
			<dl className="stat-baseline">
				<div>
					<dt>Last {recent.matches}</dt>
					<dd>{formatMetric(metric, recent[metric])}</dd>
				</div>
				<div>
					<dt>{baselineLabel}</dt>
					<dd>{formatMetric(metric, baseline[metric])}</dd>
				</div>
			</dl>
			<p className="stat-detail">{detail}</p>
		</article>
	);
}
