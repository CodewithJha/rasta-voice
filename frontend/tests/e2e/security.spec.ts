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
  await page.evaluate(async () => {
    // Test-only silent PCM checks browser media policy, never a provider response.
    const wav = new ArrayBuffer(46);
    const view = new DataView(wav);
    const label = (at: number, value: string) => {
      for (let index = 0; index < value.length; index += 1) {
        view.setUint8(at + index, value.charCodeAt(index));
      }
    };
    label(0, "RIFF"); view.setUint32(4, 38, true); label(8, "WAVE");
    label(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, 8000, true);
    view.setUint32(28, 16000, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); label(36, "data"); view.setUint32(40, 2, true);
    const url = URL.createObjectURL(new Blob([wav], { type: "audio/wav" }));
    const player = document.createElement("audio");
    try {
      await new Promise<void>((resolve, reject) => {
        player.onloadedmetadata = () => resolve();
        player.onerror = () => reject(new Error("CSP blocked the Blob media fixture"));
        player.src = url;
        player.load();
      });
    } finally {
      player.removeAttribute("src");
      player.load();
      URL.revokeObjectURL(url);
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
