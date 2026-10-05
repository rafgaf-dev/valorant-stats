export function MetricNotes() {
	return (
		<details className="metric-notes">
			<summary>How these numbers are calculated</summary>
			<ul>
				<li>
					<b>K/D</b> is kills divided by deaths. Zero deaths count as one, because apparently we have to protect the
					spreadsheet from his ego. K/D/A totals stay visible for the full readout.
				</li>
				<li>
					<b>Win rate</b> is wins divided by matches. Draws count as matches, not wins.
				</li>
				<li>
					<b>Headshot %</b> is headshot hits divided by all hits (head, body, and leg), not by shots fired.
				</li>
				<li>
					Only completed competitive matches count. Remakes are left out; surrenders count for the team that didn't
					surrender.
				</li>
				<li>
					Every number is calculated from totals, so one huge game can't skew an average of averages. The long-term
					history comes from a community archive and can have gaps.
				</li>
			</ul>
		</details>
	);
}
