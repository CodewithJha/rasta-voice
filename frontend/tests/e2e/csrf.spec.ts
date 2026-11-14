import { expect, test } from "@playwright/test";
import { E2E_DISPATCH_PASSCODE, unlockDesk } from "./unlock.ts";

test("desk browser uses signed challenge before unlock and session CSRF for writes", async ({ page }) => {
  await page.goto("/");
  const naked = await page.request.post("/api/dispatch/unlock", {
    data: { passcode: E2E_DISPATCH_PASSCODE },
  });
  expect(naked.status()).toBe(403);
  const challengeResponse = page.waitForResponse((response) => response.url().endsWith("/api/dispatch/csrf"));
  const unlockRequest = page.waitForRequest((request) => request.url().endsWith("/api/dispatch/unlock"));
  await unlockDesk(page);
  const challenge = await challengeResponse;
  expect(challenge.status()).toBe(200);
  expect(challenge.headers()["cache-control"]).toBe("no-store");
  const token = (await challenge.json()).csrf_token;
  expect((await unlockRequest).headers()["x-dispatch-csrf"]).toBe(token);
  const cookies = await page.context().cookies();
  expect(cookies.some((cookie) => cookie.name === "rasta_unlock_csrf")).toBe(false);
  expect(cookies.find((cookie) => cookie.name === "rasta_desk")?.httpOnly).toBe(true);
  const write = await page.request.post("/api/events/nonexistent/ack", { data: {} });
  expect(write.status()).toBe(403);
  const csrf = cookies.find((cookie) => cookie.name === "rasta_desk_csrf")?.value;
  expect(csrf).toBeTruthy();
  const admitted = await page.request.post("/api/events/nonexistent/ack", {
    data: {}, headers: { "X-Dispatch-CSRF": csrf!, "If-Match": '"1"' },
  });
  expect(admitted.status()).toBe(404);
});
