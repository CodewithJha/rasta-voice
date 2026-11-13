import { describe, expect, it } from "vitest";
import { DeskTape, asRecord, readRecords, type DeskRecord } from "../../src/desk-tape";

const record = (id: string, seconds: number): DeskRecord => ({
  id,
  created_at: `2026-11-13T00:00:0${seconds}.000000+00:00`,
  event: {
    intent: "delay", order_id: "18", eta_minutes: 10, urgency: "low",
    dispatch_action: "Review the new ETA", transcript: "Synthetic only", confidence: 0.5,
  },
});

describe("dispatch record boundaries", () => {
  it("rejects malformed rows instead of inventing a desk event", () => {
    for (const value of [null, {}, { id: "x" }, { ...record("A", 1), event: null }]) {
      expect(asRecord(value)).toBeNull();
    }
    expect(readRecords({ events: [null, record("A", 1), {}] })).toEqual([record("A", 1)]);
  });

  it("rejects an invalid numeric order token and string ETA", () => {
    const good = record("A", 1);
    expect(asRecord({ ...good, event: { ...good.event, order_id: 18 } })).toBeNull();
    expect(asRecord({ ...good, event: { ...good.event, eta_minutes: "10" } })).toBeNull();
  });

  it("keeps lifecycle state on the envelope and permits absent optional event values", () => {
    const good = record("A", 1);
    const parsed = asRecord({ ...good, state: "new", event: {
      ...good.event, order_id: undefined, eta_minutes: undefined,
    } });
    expect(parsed?.state).toBe("new");
    expect(parsed?.event.order_id).toBeNull();
    expect(parsed?.event.eta_minutes).toBeNull();
  });
});

describe("server-confirmed polling cursor", () => {
  it("orders unsorted fetched rows and deduplicates repeated IDs", () => {
    const tape = new DeskTape();
    expect(tape.acceptFetched([record("B", 2), record("A", 1), record("B", 2)])).toBe(2);
    expect(tape.ids).toEqual(["A", "B"]);
    expect(tape.since).toBe(record("B", 2).created_at);
  });

  it("recovers an unseen remote interval after a later local row", () => {
    const tape = new DeskTape();
    tape.acceptFetched([record("A", 1)]);
    tape.adoptLocal(record("C", 3));
    const beforeRetry = tape.url();
    expect(beforeRetry).toContain(encodeURIComponent(record("A", 1).created_at));
    // A failed fetch does not call acceptFetched. Its retry uses this same URL.
    expect(tape.url()).toBe(beforeRetry);
    expect(tape.acceptFetched([record("B", 2), record("C", 3)])).toBe(1);
    expect(tape.ids).toEqual(["A", "B", "C"]);
    expect(tape.since).toBe(record("C", 3).created_at);
  });

  it("does not move its watermark backwards on stale responses", () => {
    const tape = new DeskTape();
    tape.acceptFetched([record("C", 3)]);
    tape.acceptFetched([record("A", 1)]);
    expect(tape.ids).toEqual(["A", "C"]);
    expect(tape.since).toBe(record("C", 3).created_at);
  });
});
