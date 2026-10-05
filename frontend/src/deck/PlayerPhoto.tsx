import { useState } from "react";
import neonPortrait from "../assets/neon-portrait.webp";
import { photoUrl } from "../player";

const AGENT_ART: Record<string, string> = { Neon: neonPortrait };

/** The player's photo from the data bucket; falls back to agent art, then a placeholder. */
export function PlayerPhoto({ playerId, name, agent }: { playerId: string; name: string; agent: string }) {
	const [source, setSource] = useState<"photo" | "agent" | "none">("photo");

	if (source === "none" || (source === "agent" && !AGENT_ART[agent])) {
		return (
			<div className="picture-placeholder" role="img" aria-label={`No photo of ${name} yet`}>
				Click to add picture
			</div>
		);
	}
	return (
		<figure className="picture-frame">
			<img
				src={source === "photo" ? photoUrl(playerId) : AGENT_ART[agent]}
				alt={source === "photo" ? `Photo of ${name}` : `${agent}, ${name}'s main agent`}
				onError={() => setSource(source === "photo" ? "agent" : "none")}
			/>
		</figure>
	);
}
