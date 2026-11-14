import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { unlockDesk } from "./unlock.ts";

test.skip(process.env.RASTA_E2E_LIVE === "1", "Workflow fixture is synthetic stored data, not live speech");
const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));

function databaseCommand(source: string, ...args: string[]): string {
  const database = process.env.RASTA_E2E_DB_PATH;
  if (!database) throw new Error("The isolated Playwright database is required");
  return execFileSync("python", ["-c", source, database, ...args], {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: "backend:gnani_client:benchmark" },
    encoding: "utf8",
  }).trim();
}

test("real desk unlock, acknowledgement and resolution update the stored event and audit", async ({ page }) => {
  // Test setup writes one clearly labelled fixture to the isolated test DB.
  // The real API, cookies, CSRF, optimistic versions, polling and UI stay active.
  const id = JSON.parse(databaseCommand(`
import json, sys
from rasta.store import EventStore
store = EventStore(200, sys.argv[1])
try:
    record = store.append({"transcript": "Test-only stored fixture, not a speech result", "event": {
        "intent": "accident_sos", "order_id": "18", "eta_minutes": None,
        "urgency": "high", "dispatch_action": "Test-only fixture: contact dispatch",
        "transcript": "Test-only stored fixture", "confidence": 0.0}})
    print(json.dumps(record["id"]))
finally:
    store.close()
`)) as string;
  try {
    await page.goto("/");
    await unlockDesk(page);
    const row = page.locator(`[data-id="${id}"]`);
    await expect(row).toContainText("Test-only fixture: contact dispatch");
    await expect(row.locator(".desk-state")).toHaveText("new");
    const acknowledgement = page.waitForResponse((response) =>
      response.url().endsWith(`/api/events/${id}/ack`) && response.request().method() === "POST");
    await row.getByRole("button", { name: "Ack", exact: true }).click();
    const ack = await acknowledgement;
    expect(ack.status()).toBe(200);
    expect(ack.request().headers()["if-match"]).toBe('"1"');
    expect(ack.request().headers()["x-dispatch-csrf"]).toBeTruthy();
    expect((await ack.json()).version).toBe(2);
    await expect(row.locator(".desk-state")).toHaveText("acked");
    await expect(row.getByRole("button", { name: "Ack", exact: true })).toHaveCount(0);
    const resolution = page.waitForResponse((response) =>
      response.url().endsWith(`/api/events/${id}/resolve`) && response.request().method() === "POST");
    await row.getByRole("button", { name: "Resolve", exact: true }).click();
    const resolved = await resolution;
    expect(resolved.status()).toBe(200);
    expect(resolved.request().headers()["if-match"]).toBe('"2"');
    const record = await resolved.json();
    expect(record.state).toBe("resolved");
    expect(record.version).toBe(3);
    await expect(row.locator(".desk-state")).toHaveText("resolved");
    const audit = await page.request.get(`/api/events/${id}/audit`);
    expect(audit.status()).toBe(200);
    expect((await audit.json()).audit.map((entry: { action: string }) => entry.action))
      .toEqual(["ingest", "ack", "resolve"]);
    await page.screenshot({ path: test.info().outputPath("keyless-workflow.png"), fullPage: true });
  } finally {
    databaseCommand(`
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute("DELETE FROM audit WHERE event_id = ?", (sys.argv[2],))
    connection.execute("DELETE FROM events WHERE id = ?", (sys.argv[2],))
`, id);
  }
});
