import type { KdaMetric, Metric } from "../api";

function formatValue(value: number, kind: "kda" | "percentage") {
	return kind === "percentage" ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
}

export function StatCard({ label, metric, kind }: { label: string; metric: Metric | KdaMetric; kind: "kda" | "percentage" }) {
	const delta = metric.recent - metric.lifetime;
	const kda = kind === "kda" ? metric as KdaMetric : null;
	const commentary = delta > 0 ? "cooking" : delta < 0 ? "trolling" : "unchanged, somehow";
	return (
		<article className="stat-card">
			<div className="stat-label"><span>{label}</span><span className={delta >= 0 ? "delta positive" : "delta"}>{commentary}</span></div>
			<div className="stat-main">{formatValue(metric.recent, kind)}</div>
			<div className="stat-baseline"><span>LAST 15 <b>{formatValue(metric.recent, kind)}</b></span><span>CAREER <b>{formatValue(metric.lifetime, kind)}</b></span></div>
			{kda && <div className="stat-detail">Recent K/D/A {kda.recentKills} / {kda.recentDeaths} / {kda.recentAssists}</div>}
			{!kda && <div className="stat-detail">{metric.recentSampleSize} recent matches // {metric.lifetimeSampleSize} total</div>}
		</article>
	);
}
