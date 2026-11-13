import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const live = process.env.RASTA_E2E_LIVE === "1";
if (live && !process.env.GNANI_API_KEY) {
  throw new Error("RASTA_E2E_LIVE=1 requires a server-side GNANI_API_KEY");
}
const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0, // A live sample spends credits; never repeat it automatically.
  timeout: 40_000,
  reporter: "list",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
    screenshot: "off", // Live screenshots may contain a transcript; capture deliberately.
  },
  webServer: [
    {
      command: "python -m uvicorn rasta.main:app --host 127.0.0.1 --port 8000 --workers 1",
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      env: {
        PYTHONPATH: "backend:gnani_client:benchmark",
        GNANI_API_KEY: live ? process.env.GNANI_API_KEY! : "",
        LLM_PROVIDER: "rules",
        CORS_ALLOW_ORIGINS: "http://127.0.0.1:4173",
      },
    },
    {
      command: "npm run build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
    },
  ],
});
