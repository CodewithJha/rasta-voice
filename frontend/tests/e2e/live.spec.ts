import { expect, test } from "@playwright/test";

test.skip(process.env.RASTA_E2E_LIVE !== "1", "Opt-in real speech test: requires a key and spends two calls");

test("noisy synthetic sample produces a real request ID and reaches another desk window", async ({ page, context, request }) => {
  const health = await request.get("/api/health");
  expect((await health.json()).gnani_key_set).toBe(true);
  const desk = await context.newPage();
  await desk.goto("/");
  await page.goto("/");
  await page.getByRole("radio", { name: "Noisy line", exact: true }).click();
  const ingested = page.waitForResponse((response) =>
    response.url().includes("/api/ingest/sample") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Speak a sample line", exact: true }).click();
  const response = await ingested;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.condition).toBe("noisy");
  expect(body.ingest.stt.request_id).toEqual(expect.any(String));
  expect(body.ingest.stt.request_id.length).toBeGreaterThan(0);
  expect(body.ingest.event.intent).toBe("customer_unreachable");
  expect(body.ingest.event.order_id).toBe("18");
  await expect(page.getByRole("region", { name: "What the rider shouted over the horns" }))
    .toContainText("customer_unreachable");
  const row = desk.locator("li[data-id]").filter({ hasText: "customer unreachable" });
  await expect(row).toHaveCount(1);
  await expect(row).toHaveAttribute("data-id", body.ingest.id);
  await desk.reload();
  await expect(desk.locator(`li[data-id="${body.ingest.id}"]`)).toBeVisible();
});
