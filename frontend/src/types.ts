/** Mirror of shared/rider_event.schema.json. Keep the three copies in step. */

export type Intent =
  | "customer_unreachable"
  | "address_issue"
  | "item_missing"
  | "delay"
  | "accident_sos"
  | "other";

export type Urgency = "low" | "medium" | "high";

export interface RiderEvent {
  intent: Intent;
  order_id: string | null;
  eta_minutes: number | null;
  urgency: Urgency;
  dispatch_action: string;
  transcript: string;
  confidence: number;
}

export interface IngestResult {
  transcript: string;
  stt: {
    model: string;
    request_id: string | null;
    detected_language_code: string | null;
    processing_time: number | null;
    audio_seconds: number | null;
  };
  event: RiderEvent;
  /** Only on /api/ingest/sample: the exact line Timbre spoke. */
  sample_text?: string;
}
