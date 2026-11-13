import { expect, test } from "@playwright/test";

test.skip(process.env.RASTA_E2E_LIVE === "1", "Key-less suite uses a deliberately empty server key");

for (const width of [1280, 360, 400]) {
  test(`real no-key server renders landmarks, keyboard controls and 503 state at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const runtimeErrors: string[] = [];
    page.on("pageerror", (error) => runtimeErrors.push(error.message));
    const health = await request.get("/api/health");
    expect(health.status()).toBe(200);
    expect((await health.json()).gnani_key_set).toBe(false);
    await page.goto("/");
    await expect(page).toHaveTitle(/Rasta Voice/);
    await expect(page.getByRole("heading", { name: "Rasta Voice", exact: true })).toBeVisible();
    const rider = page.getByRole("region", { name: "What the rider shouted over the horns" });
    const slate = page.getByRole("region", { name: "Dispatch slate" });
    await expect(rider).toBeVisible();
    await expect(slate).toBeVisible();
    await expect(slate).toContainText("Dark. No drop has come in on this desk.");
    const sample = rider.getByRole("button", { name: "Speak a sample line", exact: true });
    for (let step = 0; step < 12; step++) {
      await page.keyboard.press("Tab");
      if (await sample.evaluate((element) => element === document.activeElement)) break;
    }
    await expect(sample).toBeFocused();
    const failedSample = page.waitForResponse((response) =>
      response.url().includes("/api/ingest/sample") && response.request().method() === "POST");
    await page.keyboard.press("Enter");
    expect((await failedSample).status()).toBe(503);
    await expect(rider).toContainText("The key is not set on the server.");
    await expect(sample).toBeEnabled();
    await expect(rider.getByRole("button", { name: "Hear dispatch", exact: true })).toBeDisabled();
    await expect(slate.getByRole("listitem")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(runtimeErrors).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`keyless-${width}.png`), fullPage: true });
  });
}

// Do not simulate successful controls that have not been implemented yet.
test.skip("desk unlock flow awaits issue 20", () => {});
test.skip("desk acknowledgement flow awaits issue 25", () => {});
