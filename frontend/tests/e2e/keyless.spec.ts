import { expect, test } from "@playwright/test";

import { E2E_DISPATCH_PASSCODE, unlockDesk } from "./unlock.ts";

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
    const rider = page.getByRole("region", { name: "Rider ne horns ke upar kya bola" });
    const slate = page.getByRole("region", { name: "Dispatch slate" });
    await expect(rider).toBeVisible();
    await expect(slate).toBeVisible();
    await unlockDesk(page);
    await expect(slate).toContainText("Andhera. Is desk pe abhi koi drop nahi aaya.");
    const sample = rider.getByRole("button", { name: "Ek sample line bolo", exact: true });
    for (let step = 0; step < 24; step++) {
      await page.keyboard.press("Tab");
      if (await sample.evaluate((element) => element === document.activeElement)) break;
    }
    await expect(sample).toBeFocused();
    const failedSample = page.waitForResponse((response) =>
      response.url().includes("/api/ingest/sample") && response.request().method() === "POST");
    await page.keyboard.press("Enter");
    expect((await failedSample).status()).toBe(503);
    await expect(rider).toContainText("Server pe key set nahi hai.");
    await expect(sample).toBeEnabled();
    await expect(rider.getByRole("button", { name: "Dispatch suno", exact: true })).toBeDisabled();
    await expect(slate.getByRole("listitem")).toHaveCount(0);
    await page.screenshot({ path: test.info().outputPath(`keyless-${width}.png`), fullPage: true });
    const layout = await page.evaluate(() => ({
      viewport: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflowing: Array.from(document.querySelectorAll("body *"))
        .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
        .map((element) => ({ tag: element.tagName, class: element.className,
          right: element.getBoundingClientRect().right })),
    }));
    expect(layout.scrollWidth, JSON.stringify(layout)).toBeLessThanOrEqual(layout.viewport);
    expect(runtimeErrors).toEqual([]);
  });
}

test("desk unlock rejects a wrong passcode and accepts the test fixture", async ({ page }) => {
  await page.goto("/");
  const slate = page.getByRole("region", { name: "Dispatch slate" });
  const form = page.getByRole("form", { name: "Desk unlock karo" });
  await expect(form).toBeVisible();
  await form.getByLabel("Desk passcode").fill("wrong-pass");
  await form.getByRole("button", { name: "Unlock desk" }).click();
  await expect(slate).toContainText("Polling jaari rakhne ke liye desk unlock karo.");
  await expect(form).toBeVisible();
  await form.getByLabel("Desk passcode").fill(E2E_DISPATCH_PASSCODE);
  await form.getByRole("button", { name: "Unlock desk" }).click();
  await expect(slate).toContainText("Andhera. Is desk pe abhi koi drop nahi aaya.");
  await expect(form).toBeHidden();
});

test("locale toggle switches chrome and survives a reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  const rider = page.getByRole("region", { name: "Rider ne horns ke upar kya bola" });
  await expect(rider.getByRole("button", { name: "Ek sample line bolo", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("region", { name: "What the rider shouted over the horns" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Speak a sample line", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("button", { name: "Speak a sample line", exact: true })).toBeVisible();
});
