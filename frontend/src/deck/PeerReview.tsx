import { useEffect, useRef, useState } from "react";
import { castVote, getVotes, type VoteChoice, type VoteTally } from "../api";

const LABELS: Record<VoteChoice, string> = { fair: "Fair", tooGenerous: "Too generous" };

const THANKS: Record<VoteChoice, string> = {
	fair: "Thanks. Your feedback has been noted and will be ignored.",
	tooGenerous: "Noted. Next quarter's review will be harsher.",
};

/** "Was this review fair?", one vote per viewer per day, then the results so far. */
export function PeerReview({ playerId }: { playerId: string }) {
	const [tally, setTally] = useState<VoteTally | null>(null);
	const [sending, setSending] = useState(false);
	const [notice, setNotice] = useState("");
	const results = useRef<HTMLDivElement>(null);
	const focusResults = useRef(false); // after a vote, not when the slide opens with one
	const loading = useRef<AbortController | null>(null);
	const voted = tally?.yourVote != null;

	useEffect(() => {
		const controller = new AbortController();
		loading.current = controller;
		getVotes(playerId, controller.signal).then(
			(current) => {
				if (controller.signal.aborted) return;
				setTally(current);
				if (current.yourVote) setNotice(`You already voted today: ${LABELS[current.yourVote]}.`);
			},
			() => {}, // voting still works; the results appear after a vote
		);
		return () => controller.abort();
	}, [playerId]);

	useEffect(() => {
		if (!voted || !focusResults.current) return;
		focusResults.current = false;
		results.current?.focus(); // the buttons it replaces had focus
	}, [voted]);

	async function vote(choice: VoteChoice) {
		loading.current?.abort(); // a late answer would overwrite the vote
		setSending(true);
		setNotice("");
		try {
			const { tally: updated, alreadyVoted } = await castVote(playerId, choice);
			focusResults.current = true;
			setTally(updated);
			setNotice(
				alreadyVoted && updated.yourVote
					? `You already voted today: ${LABELS[updated.yourVote]}.`
					: THANKS[choice],
			);
		} catch {
			setNotice("Your vote couldn't be sent. Try again later.");
		} finally {
			setSending(false);
		}
	}

	return (
		<div className="peer-review">
			<p className="peer-question">Was this review fair?</p>
			{!voted && (
				<div className="answers" aria-busy={sending}>
					<button type="button" className="office-button" disabled={sending} onClick={() => vote("fair")}>
						{LABELS.fair}
					</button>
					<button
						type="button"
						className="office-button green"
						disabled={sending}
						onClick={() => vote("tooGenerous")}
					>
						{LABELS.tooGenerous}
					</button>
				</div>
			)}
			{voted && tally && (
				<div className="vote-results" ref={results} tabIndex={-1}>
					<VoteChart tally={tally} />
				</div>
			)}
			<p className="vote-notice" role="status">
				{notice}
			</p>
		</div>
	);
}

function VoteChart({ tally }: { tally: VoteTally }) {
	const total = tally.fair + tally.tooGenerous;
	return (
		<figure className="vote-chart">
			<figcaption>
				Results so far: {total} {total === 1 ? "vote" : "votes"}
			</figcaption>
			{(["fair", "tooGenerous"] as const).map((choice) => {
				const share = total ? tally[choice] / total : 0;
				return (
					<div className="vote-row" key={choice}>
						<span className="vote-label">{LABELS[choice]}</span>
						<div className={`vote-bar vote-${choice}`}>
							<span className="vote-fill" style={{ width: `${share * 100}%` }} />
						</div>
						<span className="vote-count">
							{tally[choice]} ({Math.round(share * 100)}%)
						</span>
					</div>
				);
			})}
		</figure>
	);
}
