import neonPortrait from "../assets/neon-portrait.webp";

// Neon, tilted off-kilter, with a speech-bubble callout. The spin plays when the slide is
// shown (see .viewport.presenting in styles.css) and is skipped with reduced motion.
export function SpinningNeon({ caption }: { caption: string }) {
	return (
		<figure className="neon-spin">
			<img src={neonPortrait} alt="" width={640} height={782} />
			<figcaption className="callout">{caption}</figcaption>
		</figure>
	);
}
