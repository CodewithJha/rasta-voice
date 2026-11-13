import { describe, expect, it } from "vitest";

import { describeDeskError, deskNeedsUnlock } from "../../src/desk-status";
import { setLocale } from "../../src/i18n";

describe("desk unlock copy", () => {
  it("opens the unlock field on 401 and 503", () => {
    expect(deskNeedsUnlock(401)).toBe(true);
    expect(deskNeedsUnlock(503)).toBe(true);
    expect(deskNeedsUnlock(429)).toBe(false);
    expect(deskNeedsUnlock(502)).toBe(false);
    setLocale("en");
    expect(describeDeskError(401)).toBe("Unlock the desk to keep polling.");
    expect(describeDeskError(503)).toBe("Desk passcode isn't set on the server.");
    expect(describeDeskError(429)).toBe("Desk is rate-limited, polling will retry");
    setLocale("hi-en");
    expect(describeDeskError(401)).toBe("Polling jaari rakhne ke liye desk unlock karo.");
    setLocale("hi-en");
  });
});
