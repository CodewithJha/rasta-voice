import { expect, test } from "@playwright/test";
import { E2E_DISPATCH_PASSCODE, unlockDesk } from "./unlock.ts";

test.skip(process.env.RASTA_E2E_LIVE === "1", "Keyless tests use an empty server key");
for (const width of [1280, 360, 400]) {
  test(`clear rider flow and real unavailable service at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    const speechRequests: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      if (request.method() === "POST" && /\/api\/(ingest|simulate|reply)/.test(request.url())) speechRequests.push(request.url());
    });
    await page.goto("/");
    await page.getByRole("button", { name: "English", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Send a delivery update", exact: true })).toBeVisible();
    const rider = page.getByRole("region", { name: "What happened?", exact: true });
    await expect(rider).toBeVisible();
    await expect(page.locator("#dispatch-root")).toBeHidden();
    await expect(page.getByText("Speech is unavailable. The operator needs to configure the speech service.", { exact: true })).toBeVisible();
    await expect(rider.getByRole("button", { name: "Start recording", exact: true })).toBeDisabled();
    await expect(rider.getByRole("button", { name: "Try a sample", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Hear reply", exact: true })).toBeHidden();
    await expect(page.getByRole("radio", { name: "Add road noise", exact: true })).toBeHidden();
    const disclosure = page.locator(".audio-tools summary");
    await disclosure.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("radio", { name: "Add road noise", exact: true })).toBeVisible();
    const check = page.getByRole("button", { name: "Check again", exact: true });
    await check.focus();
    const ready = page.waitForResponse(response => response.url().endsWith("/api/ready"));
    await page.keyboard.press("Enter");
    expect((await ready).status()).toBe(200);
    expect(speechRequests).toEqual([]);
    // The actual service still fails closed, independently of the new preflight UI.
    expect((await request.post("/api/ingest/sample")).status()).toBe(503);
    await page.getByRole("button", { name: "Hinglish", exact: true }).click();
    await unlockDesk(page);
    const desk = page.getByRole("region", { name: "Delivery updates", exact: true });
    await expect(desk).toContainText("Abhi koi update nahi.");
    await expect(page.locator("#rider-root")).toBeHidden();
    await expect(desk.getByRole("listitem")).toHaveCount(0);
    const widthData = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    expect(widthData.document).toBeLessThanOrEqual(widthData.viewport);
    expect(errors).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`keyless-${width}.png`), fullPage: true });
  });
}
test("desk unlock rejects wrong credentials and accepts the isolated fixture", async ({ page }) => {
  await page.goto("/#dispatch");
  const desk = page.getByRole("region", { name: "Delivery updates", exact: true });
  const form = page.getByRole("form", { name: "Desk unlock karo" });
  await expect(form).toBeVisible();
  await form.getByLabel("Desk passcode").fill("wrong-pass");
  await form.getByRole("button", { name: "Unlock desk" }).click();
  await expect(form).toBeVisible();
  await expect(desk).toContainText("Updates dekhne aur sambhalne ke liye dispatcher view unlock karo.");
  await form.getByLabel("Desk passcode").fill(E2E_DISPATCH_PASSCODE);
  await form.getByRole("button", { name: "Unlock desk" }).click();
  await expect(desk).toContainText("Abhi koi update nahi.");
  await expect(form).toBeHidden();
});
test("locale persists and separate views survive navigation and reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("button", { name: "Try a sample", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.getByRole("link", { name: "Dispatch", exact: true }).click();
  await expect(page.locator("#rider-root")).toBeHidden();
  await page.reload();
  await expect(page.locator("#dispatch-title")).toBeVisible();
  await page.getByRole("link", { name: "Rider", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Send a delivery update" })).toBeVisible();
});
