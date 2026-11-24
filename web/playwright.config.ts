import { defineConfig } from "@playwright/test";

// End-to-end checks against the real FastAPI demo serving the production build.
// Run `npm run build` first. The installed Google Chrome is used, so no browser
// download is needed.
const port = 8799;
// A new registry per run, so the e2e never reuses or touches the user's demo registry.
const registry = `web/.e2e-registry/run-${Date.now()}/registry.sqlite3`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: "chrome",
    permissions: ["clipboard-read", "clipboard-write"],
  },
  webServer: {
    command: `uv run --offline --no-sync viralclip demo --port ${port} --registry ${registry}`,
    cwd: "..",
    url: `http://127.0.0.1:${port}/api/ranking`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
