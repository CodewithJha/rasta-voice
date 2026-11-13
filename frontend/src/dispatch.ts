import type { IngestResult } from "./types";
import { DeskTape, asRecord, readRecords, type DeskRecord } from "./desk-tape";
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

  const list = document.createElement("ol");
  list.className = "desk-tape";
  list.setAttribute("aria-live", "polite");
  list.setAttribute("aria-relevant", "additions");
  list.setAttribute("aria-label", "Dispatch tape");
  list.hidden = true;

  slate.append(title, status, list);
  root.append(slate);

  const tape = new DeskTape();
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
    if (tape.size === 0) {
      status.dataset.kind = "empty";
      status.textContent = EMPTY_COPY;
      list.hidden = true;
      return;
    }
    status.dataset.kind = "live";
    status.textContent = LIVE_COPY;
    list.hidden = false;
  };

  const mount = (record: DeskRecord): void => {
    const row = renderRow(record);
    const index = tape.ids.indexOf(record.id);
    const nextId = index >= 0 ? tape.ids[index + 1] : undefined;
    const next = nextId ? list.querySelector(`[data-id="${cssEscape(nextId)}"]`) : null;
    if (next) {
      list.insertBefore(row, next);
    } else {
      list.append(row);
    }
  };

  const ingestLocal = (record: DeskRecord): void => {
    if (!tape.adoptLocal(record)) {
      return;
    }
    mount(record);
    loaded = true;
    fault = undefined;
    paintChrome();
  };

  const ingestFetched = (records: DeskRecord[]): void => {
    const before = new Set(tape.ids);
    tape.acceptFetched(records);
    for (const id of tape.ids) {
      if (before.has(id)) {
        continue;
      }
      const record = records.find((item) => item.id === id);
      if (record) {
        mount(record);
      }
    }
    loaded = true;
    fault = undefined;
    paintChrome();
  };

  const pull = async (): Promise<"ok" | "backoff"> => {
    inflight?.abort();
    const controller = new AbortController();
    inflight = controller;
    const timerId = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      const response = await fetch(tape.url(), { signal: controller.signal });
      if (!response.ok) {
        loaded = true;
        fault = describeDeskError(response.status);
        paintChrome();
        return shouldBackoff(response.status) ? "backoff" : "ok";
      }
      ingestFetched(readRecords(await response.json()));
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
    ingestLocal(record);
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

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/["\\]/g, "\\$&");
}

