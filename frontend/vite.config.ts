import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin } from "vite";
import { defineConfig } from "vitest/config";

// DEV_DATA_DIR points the dev server at another data directory, such as the real summaries
// written by `make collect-local` (collector/.local/data).
const devDataDir = process.env.DEV_DATA_DIR
	? path.resolve(process.env.DEV_DATA_DIR)
	: fileURLToPath(new URL("./dev-data", import.meta.url));

// Player photos are kept out of git in config/photos/<player-id>.webp; the dev server serves
// them at the same path the data bucket uses in production.
const photoDir = fileURLToPath(new URL("../config/photos", import.meta.url));
const PHOTO_PATH = /^\/players\/([a-z0-9][a-z0-9-]*)\/photo\.webp$/;

const CONTENT_TYPES: Record<string, string> = {
	".json": "application/json",
	".webp": "image/webp",
};

// Serves summaries and player photos under /data during `vite dev`. In production the same
// paths are served from the S3 data bucket through CloudFront.
function devData(): Plugin {
	return {
		name: "dev-data",
		apply: "serve",
		configureServer(server) {
			server.middlewares.use("/data", async (request, response) => {
				const requestPath = decodeURIComponent((request.url ?? "/").split("?")[0]);
				const photo = PHOTO_PATH.exec(requestPath);
				const filePath = photo ? path.join(photoDir, `${photo[1]}.webp`) : path.join(devDataDir, requestPath);
				const root = photo ? photoDir : devDataDir;
				response.setHeader("Cache-Control", "no-store");
				try {
					if (!filePath.startsWith(root + path.sep)) throw new Error("outside the data directory");
					const body = await readFile(filePath);
					response.setHeader("Content-Type", CONTENT_TYPES[path.extname(filePath)] ?? "application/octet-stream");
					response.end(body);
				} catch {
					response.statusCode = 404;
					response.setHeader("Content-Type", "application/json");
					response.end(JSON.stringify({ error: "not_found" }));
				}
			});
		},
	};
}

const VOTES_PATH = /^\/([a-z0-9][a-z0-9-]{0,31})$/;
const VOTE_CHOICES = ["fair", "tooGenerous"];

// An in-memory stand-in for the votes function (collector/src/votes), with the same rules:
// one vote per address per player per day, and POSTs must carry the body's SHA-256, which
// CloudFront needs to sign them. Restarting the dev server clears the votes.
function devVotes(): Plugin {
	const counts = new Map<string, Record<string, number>>();
	const voters = new Map<string, string>();

	function send(response: ServerResponse, status: number, body: unknown) {
		response.statusCode = status;
		response.setHeader("Content-Type", "application/json");
		response.setHeader("Cache-Control", "no-store");
		response.end(JSON.stringify(body));
	}

	async function readBody(request: IncomingMessage): Promise<string> {
		const chunks: Buffer[] = [];
		for await (const chunk of request) chunks.push(chunk as Buffer);
		return Buffer.concat(chunks).toString("utf8");
	}

	return {
		name: "dev-votes",
		apply: "serve",
		configureServer(server) {
			server.middlewares.use("/api/votes", async (request, response) => {
				const playerId = VOTES_PATH.exec((request.url ?? "/").split("?")[0])?.[1];
				if (!playerId) return send(response, 404, { error: "not_found" });
				const tally = counts.get(playerId) ?? { fair: 0, tooGenerous: 0 };
				counts.set(playerId, tally);
				const voter = `${playerId}|${new Date().toISOString().slice(0, 10)}|${request.socket.remoteAddress}`;

				if (request.method === "GET") return send(response, 200, { ...tally, yourVote: voters.get(voter) ?? null });
				if (request.method !== "POST") return send(response, 405, { error: "method_not_allowed" });

				const body = await readBody(request);
				if (request.headers["x-amz-content-sha256"] !== createHash("sha256").update(body).digest("hex")) {
					return send(response, 403, { message: "The request signature we calculated does not match." });
				}
				let choice: unknown;
				try {
					choice = JSON.parse(body).choice;
				} catch {
					choice = undefined;
				}
				if (typeof choice !== "string" || !VOTE_CHOICES.includes(choice)) {
					return send(response, 400, { error: "invalid_choice" });
				}
				const earlier = voters.get(voter);
				if (earlier) return send(response, 409, { error: "already_voted", ...tally, yourVote: earlier });
				voters.set(voter, choice);
				tally[choice] += 1;
				send(response, 200, { ...tally, yourVote: choice });
			});
		},
	};
}

// WSL doesn't deliver file-change events for Windows drives (/mnt/c/...), so edits made
// from Windows would never reach the dev server without polling.
const onWindowsDriveInWsl = process.platform === "linux" && process.cwd().startsWith("/mnt/");

export default defineConfig({
	plugins: [react(), devData(), devVotes()],
	server: { watch: onWindowsDriveInWsl ? { usePolling: true, interval: 300 } : undefined },
	test: {
		environment: "happy-dom",
		setupFiles: ["./src/test-setup.ts"],
		restoreMocks: true,
		unstubGlobals: true,
	},
});
