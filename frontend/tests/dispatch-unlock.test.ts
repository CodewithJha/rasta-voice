import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { describeDeskError, deskNeedsUnlock } from "../src/desk-status.ts";

describe("desk unlock copy", () => {
  it("opens the unlock field on 401 and 503", () => {
    assert.equal(deskNeedsUnlock(401), true);
    assert.equal(deskNeedsUnlock(503), true);
    assert.equal(deskNeedsUnlock(429), false);
    assert.equal(deskNeedsUnlock(502), false);
    assert.equal(describeDeskError(401), "Unlock the desk to keep polling.");
    assert.equal(
      describeDeskError(503),
      "Desk passcode isn't set on the server.",
    );
    assert.equal(describeDeskError(429), "Desk is rate-limited, polling will retry");
  });
});
