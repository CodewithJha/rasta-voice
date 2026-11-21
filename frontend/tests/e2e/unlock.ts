import { expect, type Page } from "@playwright/test";

/** Matches the Playwright webServer fixture in playwright.config.ts. */
export const E2E_DISPATCH_PASSCODE = process.env.RASTA_E2E_DISPATCH_PASSCODE ?? "e2e-desk-pass";

export async function unlockDesk(page: Page, passcode = E2E_DISPATCH_PASSCODE): Promise<void> {
  if (!page.url().endsWith("#dispatch")) await page.getByRole("link", { name: "Dispatch", exact: true }).click();
  const form = page.getByRole("form", { name: "Desk unlock karo" });
  await expect(form).toBeVisible();
  await form.getByLabel("Desk passcode").fill(passcode);
  await form.getByRole("button", { name: "Unlock desk" }).click();
  await expect(form).toBeHidden();
}
