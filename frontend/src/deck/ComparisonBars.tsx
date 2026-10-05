import type { Window } from "../api";
import { METRICS, trendOf } from "../roast";
import { formatDelta, formatMetric, metricDelta, type MetricKey } from "../summary";

type Props = { recent: Window; baseline: Window; baselineLabel: string };

// The bar chart's scale: rates run to 100%, K/D to at least 2 (or the larger value, rounded up).
function scaleMax(key: MetricKey, recent: Window, baseline: Window): number {
	if (key !== "kd") return 1;
	return Math.max(2, Math.ceil(Math.max(recent.kd ?? 0, baseline.kd ?? 0)));
}

export function ComparisonBars({ recent, baseline, baselineLabel }: Props) {
	const recentLabel = `Last ${recent.matches}`;
	return (
		<div className="bars">
			<p className="bars-legend" aria-hidden="true">
				<span className="key key-recent">{recentLabel}</span>
				<span className="key key-baseline">{baselineLabel}</span>
			</p>
			{METRICS.map(({ key, label }) => {
				const max = scaleMax(key, recent, baseline);
				const delta = metricDelta(key, recent, baseline);
				return (
					<div className="bar-row" key={key}>
						<span className="bar-label">{label}</span>
						<div className="bar-pair">
							<Bar series={recentLabel} kind="recent" value={recent[key]} metric={key} max={max} />
							<Bar series={baselineLabel} kind="baseline" value={baseline[key]} metric={key} max={max} />
						</div>
						<span className={`bar-delta ${trendOf(delta)}`}>{formatDelta(key, delta)}</span>
					</div>
				);
			})}
		</div>
	);
}

type BarProps = { series: string; kind: "recent" | "baseline"; value: number | null; metric: MetricKey; max: number };

function Bar({ series, kind, value, metric, max }: BarProps) {
	const width = value === null ? 0 : Math.min(value / max, 1) * 100;
	return (
		<div className={`bar bar-${kind}`}>
			<span className="bar-fill" style={{ width: `${width}%` }} />
			<span className="bar-value">
				<span className="visually-hidden">{series}: </span>
				{formatMetric(metric, value)}
			</span>
		</div>
	);
}
