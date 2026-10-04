import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { type Plugin } from "vite";
import { defineConfig } from "vitest/config";

const devDataDir = fileURLToPath(new URL("./dev-data", import.meta.url));

// Serves sample summaries under /data during `vite dev`. In production the same
// paths are served from the S3 data bucket through CloudFront.
function devData(): Plugin {
	return {
		name: "dev-data",
		apply: "serve",
		configureServer(server) {
			server.middlewares.use("/data", async (request, response) => {
				const requestPath = decodeURIComponent((request.url ?? "/").split("?")[0]);
				const filePath = path.join(devDataDir, requestPath);
				response.setHeader("Content-Type", "application/json");
				response.setHeader("Cache-Control", "no-store");
				try {
					if (!filePath.startsWith(devDataDir + path.sep)) throw new Error("outside dev-data");
					response.end(await readFile(filePath));
				} catch {
					response.statusCode = 404;
					response.end(JSON.stringify({ error: "not_found" }));
				}
			});
		},
	};
}

export default defineConfig({
	plugins: [react(), devData()],
	test: {
		environment: "happy-dom",
		setupFiles: ["./src/test-setup.ts"],
		restoreMocks: true,
		unstubGlobals: true,
	},
});
