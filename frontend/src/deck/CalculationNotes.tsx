export function CalculationNotes() {
	return (
		<ul>
			<li>K/D is kills divided by deaths. Zero deaths count as one, to protect the spreadsheet from his ego.</li>
			<li>Win rate is wins divided by matches. Draws count as matches, not wins.</li>
			<li>Headshot % is headshot hits divided by all hits (head, body and leg), not by shots fired.</li>
			<li>
				Only completed competitive matches count. Remakes are left out; surrenders count for the team that
				didn&apos;t surrender.
			</li>
			<li>
				Every number comes from totals, so one huge game can&apos;t skew an average of averages. The long-term
				history comes from a community archive and can have gaps.
			</li>
		</ul>
	);
}
