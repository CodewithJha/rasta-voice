import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const live = process.env.RASTA_E2E_LIVE === "1";
if (live && !process.env.GNANI_API_KEY) {
  throw new Error("RASTA_E2E_LIVE=1 requires a server-side GNANI_API_KEY");
}
// Test-only desk fixture for the local Playwright server. Not a production secret.
if (!process.env.RASTA_E2E_DISPATCH_PASSCODE) {
  process.env.RASTA_E2E_DISPATCH_PASSCODE = "e2e-desk-pass";
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
    baseURL: "http://127.0.0.1:8000",
    trace: "off",
    screenshot: "off", // Live screenshots may contain a transcript; capture deliberately.
  },
  webServer: [
    {
      command: "npm --prefix frontend run build && python -m uvicorn rasta.main:app --host 127.0.0.1 --port 8000 --workers 1",
      cwd: repoRoot,
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: false,
      env: {
        PYTHONPATH: "backend:gnani_client:benchmark",
        GNANI_API_KEY: live ? process.env.GNANI_API_KEY! : "",
        LLM_PROVIDER: "rules",
        CORS_ALLOW_ORIGINS: "",
        RASTA_STATIC_DIR: "frontend/dist",
        DISPATCH_PASSCODE: process.env.RASTA_E2E_DISPATCH_PASSCODE,
      },
    },
  ],
});
