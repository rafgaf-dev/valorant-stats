import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlayerPhoto } from "./PlayerPhoto";

describe("PlayerPhoto", () => {
	it("uses the uploaded photo first", () => {
		render(<PlayerPhoto playerId="neon-main" name="Alex" agent="Neon" />);

		expect(screen.getByRole("img", { name: "Photo of Alex" })).toHaveAttribute(
			"src",
			"/data/players/neon-main/photo.webp",
		);
	});

	it("falls back to the agent art, then to a placeholder", () => {
		render(<PlayerPhoto playerId="neon-main" name="Alex" agent="Neon" />);

		fireEvent.error(screen.getByRole("img", { name: "Photo of Alex" }));
		const agentArt = screen.getByRole("img", { name: "Neon, Alex's main agent" });
		expect(agentArt.getAttribute("src")).toContain("neon-portrait");

		fireEvent.error(agentArt);
		expect(screen.getByRole("img", { name: "No photo of Alex yet" })).toHaveTextContent("Click to add picture");
	});

	it("goes straight to the placeholder for agents without art", () => {
		render(<PlayerPhoto playerId="jett-main" name="Sam" agent="Jett" />);

		fireEvent.error(screen.getByRole("img", { name: "Photo of Sam" }));

		expect(screen.getByRole("img", { name: "No photo of Sam yet" })).toBeInTheDocument();
	});
});
