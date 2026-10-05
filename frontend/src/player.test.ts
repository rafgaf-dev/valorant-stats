import { describe, expect, it } from "vitest";
import { photoUrl, playerIdFromLocation } from "./player";

describe("playerIdFromLocation", () => {
	it("uses the ?player= override in development", () => {
		expect(playerIdFromLocation("?player=stale", true)).toBe("stale");
	});

	it("ignores the override in production builds", () => {
		expect(playerIdFromLocation("?player=stale", false)).toBe("neon-main");
	});

	it("falls back to the default player", () => {
		expect(playerIdFromLocation("", true)).toBe("neon-main");
	});
});

describe("photoUrl", () => {
	it("points at the photo next to the player's summary", () => {
		expect(photoUrl("neon-main")).toBe("/data/players/neon-main/photo.webp");
		expect(photoUrl("../x")).toBe("/data/players/..%2Fx/photo.webp");
	});
});
