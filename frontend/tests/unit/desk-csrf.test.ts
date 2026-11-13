import { describe, expect, it } from "vitest";
import { deskCsrfToken } from "../../src/desk-csrf";
import { fetchWithTimeout } from "../../src/http";

describe("desk CSRF challenge", () => {
  it("reads the bounded helper's captured text after the response body is consumed", async () => {
    const original = globalThis.fetch;
    try {
      globalThis.fetch = async () => new Response(JSON.stringify({ csrf_token: "synthetic-token" }));
      const challenge = await fetchWithTimeout("/api/dispatch/csrf");
      expect(challenge.response.bodyUsed).toBe(true);
      expect(deskCsrfToken(challenge)).toBe("synthetic-token");
    } finally {
      globalThis.fetch = original;
    }
  });
  for (const text of ["not json", "null", "[]", "{}", '{"csrf_token":7}', '{"csrf_token":""}']) {
    it(`rejects an invalid challenge payload: ${text}`, () => {
      expect(() => deskCsrfToken({ response: new Response(), text })).toThrow("challenge unavailable");
    });
  }
  it("rejects a failed challenge even if the body contains a token", () => {
    expect(() => deskCsrfToken({ response: new Response(null, { status: 503 }),
      text: '{"csrf_token":"synthetic-token"}' })).toThrow("challenge unavailable");
  });
});
