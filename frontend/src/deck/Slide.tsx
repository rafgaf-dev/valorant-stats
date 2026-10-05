import type { ReactNode } from "react";

type Props = {
	number: number;
	total: number;
	title: string;
	date: string;
	layout?: "title" | "content";
	/** Replaces the plain title band with a WordArt-style title. */
	wordArt?: boolean;
	children: ReactNode;
};

// One slide in the deck, with the footer placeholders every slide in the template has:
// date on the left, footer text in the centre, slide number on the right.
export function Slide({ number, total, title, date, layout = "content", wordArt = false, children }: Props) {
	return (
		<section
			className={`slide slide-${layout}`}
			aria-roledescription="slide"
			aria-label={`Slide ${number} of ${total}: ${title}`}
		>
			{wordArt ? (
				<h2 className="word-art" data-text={title} tabIndex={-1}>
					{title}
				</h2>
			) : (
				<h2 className="title-band" tabIndex={-1}>
					{title}
				</h2>
			)}
			<div className="slide-body">{children}</div>
			<footer className="slide-footer">
				<span>{date}</span>
				<span>Unofficial fan project. Not endorsed by Riot Games.</span>
				<span>{number}</span>
			</footer>
		</section>
	);
}
