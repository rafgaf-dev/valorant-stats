import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PlayerSummary } from "../api";
import { formatDate } from "../summary";
import { PlayerPhoto } from "./PlayerPhoto";
import { Slide } from "./Slide";
import { buildSlides } from "./slides";
import { ThumbsUp } from "./ThumbsUp";
import { CELEBRATE_MS, REDUCED_CELEBRATE_MS, REVEAL_MS } from "./timing";
import { usePrefersReducedMotion } from "./usePrefersReducedMotion";

const CHECKER_COLUMNS = 8;
const CHECKER_ROWS = 6;

type Phase = "asking" | "celebrating" | "revealing" | "presenting" | "ended";

export function Deck({ summary }: { summary: PlayerSummary }) {
	const slides = useMemo(() => buildSlides(summary), [summary]);
	const total = slides.length + 1; // the question is slide 1
	const reducedMotion = usePrefersReducedMotion();
	const [phase, setPhase] = useState<Phase>("asking");
	const [index, setIndex] = useState(0);
	const viewport = useRef<HTMLDivElement>(null);
	const date = formatDate(summary.generatedAt);
	const { player } = summary;

	useEffect(() => {
		if (phase === "celebrating") {
			const timer = setTimeout(
				() => {
					setIndex(1);
					setPhase(reducedMotion ? "presenting" : "revealing");
				},
				reducedMotion ? REDUCED_CELEBRATE_MS : CELEBRATE_MS,
			);
			return () => clearTimeout(timer);
		}
		if (phase === "revealing") {
			const timer = setTimeout(() => setPhase("presenting"), REVEAL_MS);
			return () => clearTimeout(timer);
		}
	}, [phase, reducedMotion]);

	// Move focus to each new slide's title so keyboard and screen-reader users follow along.
	useEffect(() => {
		if (phase === "presenting" || phase === "asking") {
			viewport.current?.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
		}
	}, [index, phase]);

	const goTo = useCallback(
		(next: number) => {
			if (next < 0) return;
			if (next >= total) {
				setPhase("ended");
				return;
			}
			setIndex(next);
			setPhase(next === 0 ? "asking" : "presenting");
		},
		[total],
	);

	useEffect(() => {
		if (phase !== "presenting") return;
		function onKeyDown(event: KeyboardEvent) {
			if (event.altKey || event.ctrlKey || event.metaKey) return;
			if (["ArrowRight", "PageDown"].includes(event.key)) goTo(index + 1);
			else if (["ArrowLeft", "PageUp"].includes(event.key)) goTo(index - 1);
			else if (event.key === "Home") goTo(1);
			else if (event.key === "End") goTo(total - 1);
			else return;
			event.preventDefault();
		}
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, [phase, index, total, goTo]);

	if (phase === "ended") {
		return (
			<button type="button" className="end-of-show" onClick={() => goTo(1)} autoFocus>
				End of slide show, click to exit.
			</button>
		);
	}

	const current = index === 0 ? null : slides[index - 1];
	const answered = phase === "celebrating";

	return (
		<>
			{/* "presenting" starts slide animations (the Neon spin) once the reveal has finished. */}
			<div className={phase === "presenting" ? "viewport presenting" : "viewport"} ref={viewport}>
				{current === null ? (
					<Slide number={1} total={total} title={`Do you think ${player.displayName} played well recently?`} date={date} layout="title" wordArt>
						<div className="question">
							<PlayerPhoto playerId={player.id} name={player.displayName} agent={player.agent} />
							<div className="answers" role="group" aria-label="Your answer">
								<button type="button" className="office-button" onClick={() => setPhase("celebrating")} disabled={answered}>
									No
								</button>
								<button type="button" className="office-button green" onClick={() => setPhase("celebrating")} disabled={answered}>
									No
								</button>
							</div>
						</div>
					</Slide>
				) : (
					<Slide
						key={index} // a fresh element per slide, so its animations replay on every visit
						number={index + 1}
						total={total}
						title={current.title}
						date={date}
						wordArt={current.wordArt}
					>
						{current.body}
					</Slide>
				)}
				{answered && (
					<div className={`celebration${reducedMotion ? " still" : ""}`} role="status">
						<ThumbsUp className="thumbs-up" />
						<p className="correct">Correct.</p>
					</div>
				)}
				{phase === "revealing" && (
					<div className="checkerboard" aria-hidden="true">
						{Array.from({ length: CHECKER_COLUMNS * CHECKER_ROWS }, (_, cell) => {
							const column = cell % CHECKER_COLUMNS;
							const row = Math.floor(cell / CHECKER_COLUMNS);
							const delay = column * 45 + ((column + row) % 2) * 320;
							return <span key={cell} style={{ animationDelay: `${delay}ms` }} />;
						})}
					</div>
				)}
			</div>

			{phase === "presenting" && index > 0 && (
				<nav className="show-controls" aria-label="Slide show">
					<button type="button" onClick={() => goTo(index - 1)}>
						Previous
					</button>
					<span aria-live="polite">
						Slide {index + 1} of {total}
					</span>
					<button type="button" onClick={() => goTo(index + 1)}>
						{index + 1 === total ? "End show" : "Next"}
					</button>
				</nav>
			)}
		</>
	);
}
