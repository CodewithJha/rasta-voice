import type { IngestResult, RiderEvent } from "./types";
import "./dispatch.css";

const POLL_INTERVAL_MS = 2_000;
const BACKOFF_START_MS = 4_000;
const BACKOFF_MAX_MS = 32_000;
const FETCH_TIMEOUT_MS = 10_000;

const EMPTY_COPY = "Dark. No drop has come in on this desk.";
const LOADING_COPY = "Listening for the desk…";
const LIVE_COPY = "Desk is live.";
const UNLOCK_COPY = "Unlock the desk to keep polling.";
const NOT_UP_COPY = "Desk list isn't up";
const NOT_READY_COPY = "Desk isn't ready";
const UPSTREAM_COPY = "Upstream failed";
const RATE_LIMIT_COPY = "Desk is rate-limited, polling will retry";

interface DeskRecord {
  id: string;
  created_at: string;
  event: RiderEvent;
  state?: string;
}

export function initDispatch(root: HTMLElement): void {
  const slate = document.createElement("section");
  slate.className = "slate";
  slate.setAttribute("aria-labelledby", "dispatch-title");

  const title = document.createElement("h2");
  title.id = "dispatch-title";
  title.textContent = "Dispatch slate";

  const status = document.createElement("p");
  status.className = "desk-status";
  status.tabIndex = 0;
  status.dataset.kind = "loading";
  status.textContent = LOADING_COPY;

  const tape = document.createElement("ol");
  tape.className = "desk-tape";
  tape.setAttribute("aria-live", "polite");
  tape.setAttribute("aria-relevant", "additions");
  tape.setAttribute("aria-label", "Dispatch tape");
  tape.hidden = true;

  slate.append(title, status, tape);
  root.append(slate);

  const seen = new Map<string, string>();
  let lastCreatedAt: string | undefined;
  let loaded = false;
  let fault: string | undefined;
  let delay = POLL_INTERVAL_MS;
  let timer = 0;
  let inflight: AbortController | null = null;

  const paintChrome = (): void => {
    if (!loaded) {
      status.dataset.kind = "loading";
      status.textContent = LOADING_COPY;
      return;
    }
    if (fault) {
      status.dataset.kind = "error";
      status.textContent = fault;
      return;
    }
    if (seen.size === 0) {
      status.dataset.kind = "empty";
      status.textContent = EMPTY_COPY;
      tape.hidden = true;
      return;
    }
    status.dataset.kind = "live";
    status.textContent = LIVE_COPY;
    tape.hidden = false;
  };

  const adopt = (record: DeskRecord): boolean => {
    if (seen.has(record.id)) {
      return false;
    }
    seen.set(record.id, record.created_at);
    const row = renderRow(record);
    const next = nextRow(tape, record.created_at);
    if (next) {
      tape.insertBefore(row, next);
    } else {
      tape.append(row);
    }
    if (!lastCreatedAt || isLater(record.created_at, lastCreatedAt)) {
      lastCreatedAt = record.created_at;
    }
    return true;
  };

  const ingest = (records: DeskRecord[]): void => {
    let added = 0;
    for (const record of records) {
      if (adopt(record)) {
        added += 1;
      }
    }
    if (added > 0 || loaded) {
      loaded = true;
      fault = undefined;
      paintChrome();
    }
  };

  const pull = async (): Promise<"ok" | "backoff"> => {
    inflight?.abort();
    const controller = new AbortController();
    inflight = controller;
    const timerId = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    const url = lastCreatedAt
      ? `/api/events?since=${encodeURIComponent(lastCreatedAt)}`
      : "/api/events";
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        loaded = true;
        fault = describeDeskError(response.status);
        paintChrome();
        return shouldBackoff(response.status) ? "backoff" : "ok";
      }
      const records = readRecords(await response.json());
      ingest(records);
      if (!loaded) {
        loaded = true;
        fault = undefined;
        paintChrome();
      }
      return "ok";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (controller.signal.aborted && inflight !== controller) {
          return "ok";
        }
      }
      loaded = true;
      fault = UPSTREAM_COPY;
      paintChrome();
      return "backoff";
    } finally {
      window.clearTimeout(timerId);
      if (inflight === controller) {
        inflight = null;
      }
    }
  };

  const schedule = (wait: number): void => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      void tick();
    }, wait);
  };

  const tick = async (): Promise<void> => {
    const outcome = await pull();
    if (outcome === "ok") {
      delay = POLL_INTERVAL_MS;
    } else {
      delay = nextBackoff(delay);
    }
    schedule(delay);
  };

  window.addEventListener("rasta:event", (event) => {
    const record = asRecord((event as CustomEvent<IngestResult>).detail);
    if (!record) {
      return;
    }
    ingest([record]);
  });

  void tick();
}

function renderRow(record: DeskRecord): HTMLLIElement {
  const event = record.event;
  const row = document.createElement("li");
  row.className = "desk-row";
  row.dataset.id = record.id;
  row.dataset.createdAt = record.created_at;

  const main = document.createElement("div");
  main.className = "desk-row-main";

  if (event.intent === "accident_sos") {
    const sos = document.createElement("span");
    sos.className = "desk-sos";
    sos.textContent = "SOS";
    main.append(sos);
  }

  const intent = document.createElement("span");
  intent.className = "desk-intent";
  intent.textContent = event.intent.replaceAll("_", " ");
  main.append(intent);

  const order = document.createElement("span");
  order.className = "desk-order";
  order.textContent = event.order_id ? `order ${event.order_id}` : "order —";
  main.append(order);

  const eta = document.createElement("span");
  eta.className = "desk-eta";
  eta.textContent = event.eta_minutes === null ? "eta —" : `eta ${event.eta_minutes} min`;
  main.append(eta);

  const urgency = document.createElement("span");
  const level = event.urgency;
  urgency.className = level === "high" ? "desk-urgency desk-urgency-high" : "desk-urgency";
  urgency.textContent = level === "high" ? "HIGH" : level;
  main.append(urgency);

  const action = document.createElement("p");
  action.className = "desk-action";
  action.textContent = event.dispatch_action;
  action.title = event.dispatch_action;

  const acks = document.createElement("div");
  acks.className = "desk-acks";
  acks.setAttribute("aria-hidden", "true");

  row.append(main, action);
  if (record.state) {
    const state = document.createElement("span");
    state.className = "desk-state";
    state.textContent = record.state;
    row.append(state);
  }
  row.append(acks);
  return row;
}

function nextRow(tape: HTMLOListElement, createdAt: string): HTMLLIElement | null {
  for (const child of Array.from(tape.children)) {
    if (!(child instanceof HTMLLIElement)) {
      continue;
    }
    const stamp = child.dataset.createdAt;
    if (stamp && isLater(stamp, createdAt)) {
      return child;
    }
  }
  return null;
}

function readRecords(body: unknown): DeskRecord[] {
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

function asRecord(value: unknown): DeskRecord | null {
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

function describeDeskError(status: number): string {
  if (status === 401) return UNLOCK_COPY;
  if (status === 404) return NOT_UP_COPY;
  if (status === 429) return RATE_LIMIT_COPY;
  if (status === 503) return NOT_READY_COPY;
  if (status === 502) return UPSTREAM_COPY;
  return `Desk failed (${status}).`;
}

function shouldBackoff(status: number): boolean {
  return status === 401 || status === 422 || status === 429 || status === 502 || status === 503;
}

function nextBackoff(current: number): number {
  if (current < BACKOFF_START_MS) {
    return BACKOFF_START_MS;
  }
  return Math.min(current * 2, BACKOFF_MAX_MS);
}

function isLater(left: string, right: string): boolean {
  const a = Date.parse(left);
  const b = Date.parse(right);
  if (!Number.isNaN(a) && !Number.isNaN(b) && a !== b) {
    return a > b;
  }
  return left > right;
}
