import { readFile } from "node:fs/promises";
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

// WSL doesn't deliver file-change events for Windows drives (/mnt/c/...), so edits made
// from Windows would never reach the dev server without polling.
const onWindowsDriveInWsl = process.platform === "linux" && process.cwd().startsWith("/mnt/");

export default defineConfig({
	plugins: [react(), devData()],
	server: { watch: onWindowsDriveInWsl ? { usePolling: true, interval: 300 } : undefined },
	test: {
		environment: "happy-dom",
		setupFiles: ["./src/test-setup.ts"],
		restoreMocks: true,
		unstubGlobals: true,
	},
});
