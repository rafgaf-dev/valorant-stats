/** The player to show: the build's VITE_PLAYER_ID, or ?player=<id> in development. */
export function playerIdFromLocation(search: string, isDev: boolean): string {
	// In development, ?player=<id> previews the other sample states in frontend/dev-data.
	const override = isDev ? new URLSearchParams(search).get("player") : null;
	return override || import.meta.env.VITE_PLAYER_ID || "neon-main";
}

/** The player's photo, uploaded next to their summary; kept out of git (see README). */
export function photoUrl(playerId: string): string {
	return `/data/players/${encodeURIComponent(playerId)}/photo.webp`;
}
