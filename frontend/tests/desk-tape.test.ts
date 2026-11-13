import assert from "node:assert/strict";
import { test } from "node:test";

import { DeskTape, eventsUrl, type DeskRecord } from "../src/desk-tape.ts";

function drop(id: string, createdAt: string): DeskRecord {
  return {
    id,
    created_at: createdAt,
    event: {
      intent: "delay",
      order_id: id,
      eta_minutes: 10,
      urgency: "low",
      dispatch_action: `Handle ${id}`,
      transcript: "",
      confidence: 0.5,
    },
  };
}

test("a local later row does not skip an unfetched remote interval, including after a failed poll", () => {
  const tape = new DeskTape();
  const first = drop("A", "2026-11-13T04:00:00.000000+00:00");
  const remote = drop("B", "2026-11-13T04:00:02.000000+00:00");
  const local = drop("C", "2026-11-13T04:00:03.000000+00:00");

  assert.equal(tape.acceptFetched([first]), 1);
  assert.deepEqual(tape.ids, ["A"]);
  assert.equal(tape.url(), eventsUrl(first.created_at));

  assert.equal(tape.adoptLocal(local), true);
  assert.deepEqual(tape.ids, ["A", "C"]);
  // Watermark stays at t1 so the next GET cannot skip B.
  assert.equal(tape.since, first.created_at);
  assert.equal(tape.url(), eventsUrl(first.created_at));

  // A failed poll must not advance the cursor.
  assert.equal(tape.since, first.created_at);
  assert.equal(tape.url(), eventsUrl(first.created_at));

  assert.equal(tape.acceptFetched([remote, local]), 1);
  assert.deepEqual(tape.ids, ["A", "B", "C"]);
  assert.equal(tape.since, local.created_at);
  assert.equal(tape.url(), eventsUrl(local.created_at));
});
