import { describe, expect, it } from "vitest";

import { en, type MessageKey } from "../../src/i18n/en";
import { hiEn } from "../../src/i18n/hi-en";
import { DEFAULT_LOCALE, getLocale, missingHiEnKeys, setLocale, t } from "../../src/i18n";

describe("i18n catalogue", () => {
  it("defaults to Hinglish and keeps every hi-en key", () => {
    expect(DEFAULT_LOCALE).toBe("hi-en");
    expect(getLocale()).toBe("hi-en");
    expect(missingHiEnKeys()).toEqual([]);
    const keys = Object.keys(en) as MessageKey[];
    expect(Object.keys(hiEn).sort()).toEqual([...keys].sort());
  });

  it("falls back to English when a hi-en string is missing", () => {
    const partial = { ...hiEn };
    delete (partial as { "rider.talk"?: string })["rider.talk"];
    expect(missingHiEnKeys(partial)).toEqual(["rider.talk"]);
  });

  it("switches chrome and interpolates, without rewriting a transcript", () => {
    const spoken = "Customer 18 unreachable at gate 4";
    setLocale("hi-en");
    expect(t("rider.sample")).toBe("Ek sample line bolo");
    expect(t("desk.failed", { status: 500 })).toBe("Desk fail ho gaya (500).");
    setLocale("en");
    expect(t("rider.sample")).toBe("Speak a sample line");
    expect(t("error.missingKey")).toBe("The key is not set on the server.");
    expect(spoken).toBe("Customer 18 unreachable at gate 4");
    setLocale("hi-en");
  });
});
