import { describe, expect, it } from "vitest";

import { chitSummary } from "../../src/chit-view";
import { setLocale } from "../../src/i18n";
import type { IngestResult } from "../../src/types";

const ingest: IngestResult = {
  transcript: "Order 18, customer not answering",
  stt: {
    model: "prisma",
    request_id: "req-42",
    detected_language_code: "en",
    processing_time: 1,
    audio_seconds: 2,
  },
  event: {
    intent: "customer_unreachable",
    order_id: "18",
    eta_minutes: 12,
    urgency: "high",
    dispatch_action: "Call the customer",
    transcript: "Order 18, customer not answering",
    confidence: 0.8,
  },
};

describe("human chit summary", () => {
  it("exposes typography fields and keeps the raw request_id and transcript", () => {
    setLocale("en");
    const summary = chitSummary(ingest);
    expect(summary.intent).toBe("customer unreachable");
    expect(summary.order).toBe("18");
    expect(summary.eta).toBe("12 min");
    expect(summary.urgency).toBe("high");
    expect(summary.action).toBe("Call the customer");
    expect(summary.transcript).toBe("Order 18, customer not answering");
    expect(summary.requestId).toBe("req-42");
    setLocale("hi-en");
    const again = chitSummary(ingest);
    expect(again.transcript).toBe("Order 18, customer not answering");
    expect(again.requestId).toBe("req-42");
    setLocale("hi-en");
  });
});
