import { describe, expect, it } from "vitest";

import { describeError, describeNetworkError } from "../../src/errors";
import { setLocale } from "../../src/i18n";

describe("named speech errors", () => {
  it("does not treat a spent budget as a missing key", () => {
    setLocale("en");
    expect(
      describeError(503, JSON.stringify({ detail: "The public speech budget is exhausted." })),
    ).toBe("The public speech budget is exhausted.");
    expect(
      describeError(503, JSON.stringify({ detail: "Public speech is paused." })),
    ).toBe("Public speech is paused.");
    expect(
      describeError(503, JSON.stringify({ detail: "GNANI_API_KEY is not set" })),
    ).toBe("The key is not set on the server.");
    expect(describeError(503, "")).toBe("The key is not set on the server.");
    expect(describeError(429, "{}")).toBe("The demo is busy, try in a minute.");
    expect(
      describeError(
        503,
        JSON.stringify({
          error: { code: "budget_exhausted", message: "The public speech budget is exhausted.", request_id: "req-1" },
        }),
      ),
    ).toBe("The public speech budget is exhausted.");
    setLocale("hi-en");
    expect(
      describeError(503, JSON.stringify({ detail: "The public speech budget is exhausted." })),
    ).toBe("Public speech budget khatam ho gaya hai.");
    setLocale("hi-en");
  });

  it("names timeouts", () => {
    setLocale("en");
    expect(describeNetworkError(new DOMException("aborted", "AbortError"))).toBe(
      "The request timed out. Try again.",
    );
    setLocale("hi-en");
  });
});
