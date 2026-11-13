/** Poll watermark and row order for the dispatch tape. CSS-free so it can be tested. */

import type { RiderEvent } from "./types";

export interface DeskRecord {
  id: string;
  created_at: string;
  event: RiderEvent;
  state?: string;
  version?: number;
  rider_id?: string;
  ack_at?: string | null;
  updated_at?: string;
}

export function eventsUrl(since?: string): string {
  return since
    ? `/api/events?updated_since=${encodeURIComponent(since)}`
    : "/api/events";
}

export function changeStamp(record: DeskRecord): string {
  return record.updated_at || record.created_at;
}

export function isLater(left: string, right: string): boolean {
  const a = Date.parse(left);
  const b = Date.parse(right);
  if (!Number.isNaN(a) && !Number.isNaN(b) && a !== b) {
    return a > b;
  }
  return left > right;
}

export class DeskTape {
  readonly ids: string[] = [];
  private readonly stamps = new Map<string, string>();
  private watermark: string | undefined;

  get size(): number {
    return this.ids.length;
  }

  get since(): string | undefined {
    return this.watermark;
  }

  url(): string {
    return eventsUrl(this.watermark);
  }

  /** Paint a local / fast-path row without moving the poll cursor. */
  adoptLocal(record: DeskRecord): boolean {
    return this.insert(record);
  }

  /**
   * Adopt fetched records, then advance the watermark to the latest
   * ``created_at`` in that response, even if some rows were already on the tape.
   */
  acceptFetched(records: DeskRecord[]): number {
    let added = 0;
    for (const record of records) {
      if (this.insert(record)) {
        added += 1;
      }
    }
    for (const record of records) {
      const stamp = changeStamp(record);
      if (!this.watermark || isLater(stamp, this.watermark)) {
        this.watermark = stamp;
      }
    }
    return added;
  }

  private insert(record: DeskRecord): boolean {
    if (this.stamps.has(record.id)) {
      return false;
    }
    this.stamps.set(record.id, record.created_at);
    const index = this.ids.findIndex((id) => {
      const stamp = this.stamps.get(id);
      return Boolean(stamp && isLater(stamp, record.created_at));
    });
    if (index === -1) {
      this.ids.push(record.id);
    } else {
      this.ids.splice(index, 0, record.id);
    }
    return true;
  }
}

export function readRecords(body: unknown): DeskRecord[] {
  if (!body || typeof body !== "object" || !("events" in body)) {
    return [];
  }
  const events = (body as { events: unknown }).events;
  if (!Array.isArray(events)) {
    return [];
  }
  const records: DeskRecord[] = [];
  for (const item of events) {
    const record = asRecord(item);
    if (record) {
      records.push(record);
    }
  }
  return records;
}

export function asRecord(value: unknown): DeskRecord | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const row = value as Record<string, unknown>;
  if (typeof row.id !== "string" || row.id.length === 0) {
    return null;
  }
  if (typeof row.created_at !== "string" || row.created_at.length === 0) {
    return null;
  }
  const event = asEvent(row.event);
  if (!event) {
    return null;
  }
  const record: DeskRecord = { id: row.id, created_at: row.created_at, event };
  if (typeof row.state === "string" && row.state.length > 0) {
    record.state = row.state;
  }
  if (typeof row.version === "number" && Number.isFinite(row.version)) {
    record.version = row.version;
  }
  if (typeof row.rider_id === "string" && row.rider_id.length > 0) {
    record.rider_id = row.rider_id;
  }
  if (row.ack_at === null || typeof row.ack_at === "string") {
    record.ack_at = row.ack_at;
  }
  if (typeof row.updated_at === "string" && row.updated_at.length > 0) {
    record.updated_at = row.updated_at;
  }
  return record;
}

function asEvent(value: unknown): RiderEvent | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const event = value as Record<string, unknown>;
  if (typeof event.intent !== "string" || typeof event.urgency !== "string") {
    return null;
  }
  if (typeof event.dispatch_action !== "string") {
    return null;
  }
  const orderId = event.order_id;
  const eta = event.eta_minutes;
  if (orderId !== null && orderId !== undefined && typeof orderId !== "string") {
    return null;
  }
  if (eta !== null && eta !== undefined && typeof eta !== "number") {
    return null;
  }
  return {
    intent: event.intent as RiderEvent["intent"],
    order_id: typeof orderId === "string" ? orderId : null,
    eta_minutes: typeof eta === "number" ? eta : null,
    urgency: event.urgency as RiderEvent["urgency"],
    dispatch_action: event.dispatch_action,
    transcript: typeof event.transcript === "string" ? event.transcript : "",
    confidence: typeof event.confidence === "number" ? event.confidence : 0,
  };
}
