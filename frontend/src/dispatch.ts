import { deskCsrfToken } from "./desk-csrf";
import type { IngestResult } from "./types";
import { DeskTape, asRecord, readRecords, type DeskRecord } from "./desk-tape";
import { describeDeskError, deskNeedsUnlock } from "./desk-status";
import { describeNetworkError } from "./errors";
import { fetchWithTimeout } from "./http";
import { onLocaleChange, t } from "./i18n";
import "./dispatch.css";

const POLL_INTERVAL_MS = 2_000;
const BACKOFF_START_MS = 4_000;
const BACKOFF_MAX_MS = 32_000;
const USAGE_INTERVAL_MS = 15_000;
const CSRF_COOKIE = "rasta_desk_csrf";

export function initDispatch(root: HTMLElement): void {
  const slate = document.createElement("section");
  slate.className = "slate";
  slate.setAttribute("aria-labelledby", "dispatch-title");

  const title = document.createElement("h2");
  title.id = "dispatch-title";

  const status = document.createElement("p");
  status.className = "desk-status";
  status.tabIndex = 0;
  status.dataset.kind = "loading";

  const list = document.createElement("ol");
  list.className = "desk-tape";
  list.setAttribute("aria-live", "polite");
  list.setAttribute("aria-relevant", "additions");
  list.hidden = true;

  const form = document.createElement("form");
  form.className = "desk-unlock";
  form.hidden = true;

  const label = document.createElement("label");
  label.className = "desk-unlock-label";
  const labelText = document.createElement("span");
  const input = document.createElement("input");
  input.type = "password";
  input.name = "passcode";
  input.autocomplete = "current-password";
  input.required = true;
  input.minLength = 1;
  label.append(labelText, input);

  const button = document.createElement("button");
  button.type = "submit";
  form.append(label, button);

  const banner = document.createElement("p");
  banner.className = "desk-banner";
  banner.hidden = true;
  banner.setAttribute("aria-live", "assertive");

  const usage = document.createElement("p");
  usage.className = "desk-usage";
  usage.hidden = true;

  const mute = document.createElement("button");
  mute.type = "button";
  mute.className = "desk-mute";

  slate.append(title, status, form, banner, usage, list);
  root.append(slate);

  const tape = new DeskTape();
  let loaded = false;
  let fault: string | undefined;
  let unlockOpen = false;
  let delay = POLL_INTERVAL_MS;
  let timer = 0;
  let inflight: AbortController | null = null;
  let usageTimer = 0;
  let sosMuted = false;
  const heardSos = new Set<string>();
  const records = new Map<string, DeskRecord>();

  const paintChrome = (): void => {
    form.hidden = !unlockOpen;
    if (!loaded) {
      status.dataset.kind = "loading";
      status.textContent = t("desk.loading");
      return;
    }
    if (fault) {
      status.dataset.kind = "error";
      status.textContent = fault;
      return;
    }
    if (tape.size === 0) {
      status.dataset.kind = "empty";
      status.textContent = t("desk.empty");
      list.hidden = true;
      return;
    }
    status.dataset.kind = "live";
    status.textContent = t("desk.live");
    list.hidden = false;
    paintAlerts();
  };

  const paintLabels = (): void => {
    title.textContent = t("desk.title");
    list.setAttribute("aria-label", t("desk.tapeLabel"));
    form.setAttribute("aria-label", t("desk.unlockForm"));
    labelText.textContent = t("desk.passcode");
    button.textContent = t("desk.unlock");
    mute.textContent = sosMuted ? t("desk.unmuteSos") : t("desk.muteSos");
    banner.textContent = t("desk.sosBanner");
    paintChrome();
  };
  paintLabels();


  const paintAlerts = (): void => {
    const live = [...records.values()].filter(
      (item) => item.event.intent === "accident_sos" && (item.state === "new" || item.state === "escalated" || !item.state),
    );
    banner.hidden = live.length === 0;
    if (!banner.hidden) {
      banner.textContent = t("desk.sosBanner");
    }
  };

  const playSosIfNeeded = (record: DeskRecord): void => {
    if (record.event.intent !== "accident_sos") {
      return;
    }
    if (record.state && record.state !== "new" && record.state !== "escalated") {
      return;
    }
    if (heardSos.has(record.id) || sosMuted) {
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      heardSos.add(record.id);
      return;
    }
    heardSos.add(record.id);
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = 680;
      gain.gain.value = 0.04;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.18);
      window.setTimeout(() => {
        void ctx.close();
      }, 300);
    } catch {
      /* tone is best-effort */
    }
  };

  const readCsrf = (): string => {
    const prefix = `${CSRF_COOKIE}=`;
    for (const part of document.cookie.split("; ")) {
      if (part.startsWith(prefix)) {
        return decodeURIComponent(part.slice(prefix.length));
      }
    }
    return "";
  };

  const remember = (record: DeskRecord): void => {
    records.set(record.id, record);
    playSosIfNeeded(record);
    paintAlerts();
  };

  const refreshRow = (record: DeskRecord): void => {
    remember(record);
    const existing = list.querySelector(`[data-id="${cssEscape(record.id)}"]`);
    const row = renderRow(record, { onAck: (item) => void act(item, "ack"), onResolve: (item) => void act(item, "resolve") });
    if (existing) {
      existing.replaceWith(row);
    }
  };

  const act = async (record: DeskRecord, action: "ack" | "resolve"): Promise<void> => {
    const version = record.version ?? 1;
    const csrf = readCsrf();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "If-Match": `"${version}"`,
    };
    if (csrf) {
      headers["X-Dispatch-CSRF"] = csrf;
    }
    const showOn = (item: DeskRecord, message: string): void => {
      const row = list.querySelector(`[data-id="${cssEscape(item.id)}"]`);
      if (!row) {
        return;
      }
      let note = row.querySelector(".desk-row-msg");
      if (!note) {
        note = document.createElement("p");
        note.className = "desk-row-msg";
        row.append(note);
      }
      note.textContent = message;
    };
    const refreshCurrent = async (): Promise<DeskRecord | undefined> => {
      try {
        const { response, text } = await fetchWithTimeout(
          `/api/events/${encodeURIComponent(record.id)}`,
          { credentials: "same-origin" },
        );
        if (!response.ok) {
          void pull();
          return undefined;
        }
        const current = asRecord(JSON.parse(text));
        if (current) {
          refreshRow(current);
          return current;
        }
      } catch {
        void pull();
      }
      return undefined;
    };
    try {
      const { response, text } = await fetchWithTimeout(`/api/events/${encodeURIComponent(record.id)}/${action}`, {
        method: "POST",
        credentials: "same-origin",
        headers,
        body: "{}",
      });
      if (response.status === 409) {
        const current = await refreshCurrent();
        showOn(current ?? record, t("desk.changed"));
        return;
      }
      if (!response.ok) {
        showOn(record, describeDeskError(response.status));
        return;
      }
      const updated = asRecord(JSON.parse(text));
      if (updated) {
        refreshRow(updated);
      }
    } catch {
      await refreshCurrent();
      showOn(record, describeDeskError(0));
    }
  };

  const paintUsage = (body: { demo_credits_remaining?: unknown; sos_unacked?: unknown }): void => {
    const credits = body.demo_credits_remaining;
    const sos = body.sos_unacked;
    if (typeof credits !== "number" || typeof sos !== "number") {
      usage.hidden = true;
      usage.textContent = "";
      return;
    }
    usage.hidden = false;
    usage.textContent = `${t("desk.usageCredits")}: ${credits} · ${t("desk.usageSos")}: ${sos}`;
    if (!usage.contains(mute)) {
      usage.append(mute);
    }
  };

  const pullUsage = async (): Promise<void> => {
    try {
      const { response, text } = await fetchWithTimeout("/api/admin/usage", {
        credentials: "same-origin",
      });
      if (!response.ok) {
        usage.hidden = true;
        return;
      }
      paintUsage(JSON.parse(text) as { demo_credits_remaining?: unknown; sos_unacked?: unknown });
    } catch {
      usage.hidden = true;
    }
  };

  mute.addEventListener("click", () => {
    sosMuted = !sosMuted;
    mute.textContent = sosMuted ? t("desk.unmuteSos") : t("desk.muteSos");
  });

  const mount = (record: DeskRecord): void => {
    remember(record);
    const row = renderRow(record, { onAck: (item) => void act(item, "ack"), onResolve: (item) => void act(item, "resolve") });
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
    // Keep the unlock field up if the desk poll is still locked; the rider
    // event can still appear on the tape in the same tab.
    if (!unlockOpen) {
      fault = undefined;
    }
    paintChrome();
  };

  const ingestFetched = (incoming: DeskRecord[]): void => {
    const before = new Set(tape.ids);
    tape.acceptFetched(incoming);
    for (const record of incoming) {
      if (before.has(record.id)) {
        refreshRow(record);
      } else if (tape.ids.includes(record.id)) {
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
    try {
      const { response, text } = await fetchWithTimeout(tape.url(), {
        signal: controller.signal,
        credentials: "same-origin",
      });
      if (!response.ok) {
        loaded = true;
        fault = describeDeskError(response.status);
        unlockOpen = deskNeedsUnlock(response.status);
        paintChrome();
        return shouldBackoff(response.status) ? "backoff" : "ok";
      }
      unlockOpen = false;
      ingestFetched(readRecords(JSON.parse(text)));
      return "ok";
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (controller.signal.aborted && inflight !== controller) {
          return "ok";
        }
      }
      loaded = true;
      fault = describeNetworkError(err);
      paintChrome();
      return "backoff";
    } finally {
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

  const unlockDesk = async (passcode: string): Promise<void> => {
    inflight?.abort();
    const controller = new AbortController();
    inflight = controller;
    try {
      const challenge = await fetchWithTimeout("/api/dispatch/csrf", {
        credentials: "same-origin", signal: controller.signal,
      });
      const csrf = deskCsrfToken(challenge);
      const { response } = await fetchWithTimeout("/api/dispatch/unlock", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Dispatch-CSRF": csrf },
        body: JSON.stringify({ passcode }),
        signal: controller.signal,
      });
      if (!response.ok) {
        loaded = true;
        fault = describeDeskError(response.status);
        unlockOpen = true;
        paintChrome();
        return;
      }
      unlockOpen = false;
      fault = undefined;
      delay = POLL_INTERVAL_MS;
      void tick();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        if (controller.signal.aborted && inflight !== controller) {
          return;
        }
      }
      loaded = true;
      fault = describeNetworkError(err);
      unlockOpen = true;
      paintChrome();
    } finally {
      if (inflight === controller) {
        inflight = null;
      }
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const passcode = input.value;
    input.value = "";
    void unlockDesk(passcode);
  });

  onLocaleChange(paintLabels);

  window.addEventListener("rasta:event", (event) => {
    const record = asRecord((event as CustomEvent<IngestResult>).detail);
    if (!record) {
      return;
    }
    ingestLocal(record);
  });

  void tick();
  void pullUsage();
  window.clearInterval(usageTimer);
  usageTimer = window.setInterval(() => {
    void pullUsage();
  }, USAGE_INTERVAL_MS);
}


function renderRow(
  record: DeskRecord,
  actions?: {
    onAck: (record: DeskRecord) => void;
    onResolve: (record: DeskRecord) => void;
  },
): HTMLLIElement {
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

  const state = record.state ?? "new";
  const canAck = state === "new" || state === "escalated";
  const canResolve = state === "acked" || (state === "escalated" && Boolean(record.ack_at));
  if (actions && (canAck || canResolve)) {
    if (canAck) {
      const ack = document.createElement("button");
      ack.type = "button";
      ack.className = "desk-action-button";
      ack.textContent = t("desk.ack");
      ack.addEventListener("click", () => actions.onAck(record));
      acks.append(ack);
    }
    if (canResolve) {
      const resolve = document.createElement("button");
      resolve.type = "button";
      resolve.className = "desk-action-button";
      resolve.textContent = t("desk.resolve");
      resolve.addEventListener("click", () => actions.onResolve(record));
      acks.append(resolve);
    }
  } else {
    acks.setAttribute("aria-hidden", "true");
  }

  row.append(main, action);
  const stateEl = document.createElement("span");
  stateEl.className = "desk-state";
  stateEl.textContent = state;
  row.append(stateEl);
  if (record.rider_id) {
    const rider = document.createElement("span");
    rider.className = "desk-order";
    rider.textContent = record.rider_id;
    row.append(rider);
  }
  row.append(acks);
  return row;
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

