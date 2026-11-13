import { expect, test } from "@playwright/test";

test("built UI obeys real CSP, loads its worklet, and blocks external scripts", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.locator("#rider-title")).toBeVisible();
  await expect(page.locator("#dispatch-title")).toBeVisible();
  await page.evaluate(async () => {
    const context = new AudioContext();
    try {
      await context.audioWorklet.addModule("/pcm-worklet.js");
      const node = new AudioWorkletNode(context, "rasta-pcm");
      node.disconnect();
    } finally {
      await context.close();
    }
  });
  const blocked = await page.evaluate(() => new Promise<string>((resolve) => {
    document.addEventListener("securitypolicyviolation", (event) => {
      if (event.blockedURI === "https://example.com/not-allowed.js") {
        resolve(event.effectiveDirective);
      }
    });
    const script = document.createElement("script");
    script.src = "https://example.com/not-allowed.js";
    document.head.append(script);
  }));
  expect(blocked).toMatch(/^script-src/);
});
