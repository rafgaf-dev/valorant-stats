// A thumbs-up in the style of early-2000s office clip art: flat fills, a heavy outline,
// one glossy highlight, and a few sparkles.
export function ThumbsUp({ className }: { className?: string }) {
	return (
		<svg className={className} viewBox="0 0 200 200" role="img" aria-label="Thumbs up">
			<g stroke="#1F497D" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round">
				<rect x="34" y="108" width="44" height="76" rx="7" fill="#4F81BD" />
				<rect x="34" y="108" width="12" height="76" rx="5" fill="#95B3D7" stroke="none" />
				<path
					d="M76 104 C 82 96, 92 94, 98 92 C 104 70, 98 46, 110 32 C 120 22, 136 28, 134 46 C 132 62, 124 76, 124 88 L 160 88 C 176 88, 178 108, 166 112 C 178 116, 176 134, 164 136 C 174 140, 172 158, 160 160 C 168 166, 164 182, 150 182 L 92 182 C 84 182, 78 176, 76 168 Z"
					fill="#FFC000"
				/>
				<path d="M124 112 L 164 112 M 124 136 L 162 136 M 124 160 L 158 160" fill="none" />
				<path d="M108 42 C 104 58, 106 76, 102 92" fill="none" stroke="#FFF2CC" strokeWidth="6" opacity="0.9" />
			</g>
			<g fill="#F79646">
				<path d="M170 30 l5 13 13 5 -13 5 -5 13 -5 -13 -13 -5 13 -5 z" />
				<path d="M40 52 l4 10 10 4 -10 4 -4 10 -4 -10 -10 -4 10 -4 z" />
				<path d="M182 92 l3 8 8 3 -8 3 -3 8 -3 -8 -8 -3 8 -3 z" />
			</g>
		</svg>
	);
}
