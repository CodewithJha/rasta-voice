/** Human typography for a successful ingest. Transcripts stay as Prisma returned them. */

import { t } from "./i18n";
import type { IngestResult } from "./types";

export function fillChitResult(out: HTMLElement, ingest: IngestResult): void {
  out.replaceChildren();
  out.classList.add("chit-result");

  const facts = document.createElement("dl");
  facts.className = "chit-facts";
  const event = ingest.event;
  addFact(facts, t("chit.intent"), event.intent.replaceAll("_", " "));
  addFact(facts, t("chit.order"), event.order_id ? event.order_id : t("chit.orderNone"));
  addFact(
    facts,
    t("chit.eta"),
    event.eta_minutes === null ? t("chit.etaNone") : `${event.eta_minutes} ${t("chit.minutes")}`,
  );
  addFact(facts, t("chit.urgency"), event.urgency);
  addFact(facts, t("chit.action"), event.dispatch_action);
  out.append(facts);

  if (ingest.transcript || event.transcript) {
    const spoken = document.createElement("p");
    spoken.className = "chit-transcript";
    const label = document.createElement("span");
    label.className = "chit-transcript-label";
    label.textContent = t("chit.transcript");
    const body = document.createElement("span");
    body.className = "chit-transcript-text";
    body.textContent = ingest.transcript || event.transcript;
    spoken.append(label, body);
    out.append(spoken);
  }

  const raw = document.createElement("details");
  raw.className = "chit-raw";
  const summary = document.createElement("summary");
  const requestId = ingest.stt?.request_id ?? "";
  summary.textContent = requestId ? `${t("chit.raw")} · ${requestId}` : t("chit.raw");
  const pre = document.createElement("pre");
  pre.tabIndex = 0;
  pre.textContent = JSON.stringify(ingest, null, 2);
  raw.append(summary, pre);
  out.append(raw);
}

function addFact(list: HTMLDListElement, term: string, value: string): void {
  const row = document.createElement("div");
  row.className = "chit-fact";
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = value;
  row.append(dt, dd);
  list.append(row);
}

export function chitSummary(ingest: IngestResult): {
  intent: string;
  order: string;
  eta: string;
  urgency: string;
  action: string;
  transcript: string;
  requestId: string | null;
} {
  const event = ingest.event;
  return {
    intent: event.intent.replaceAll("_", " "),
    order: event.order_id ? event.order_id : t("chit.orderNone"),
    eta: event.eta_minutes === null ? t("chit.etaNone") : `${event.eta_minutes} ${t("chit.minutes")}`,
    urgency: event.urgency,
    action: event.dispatch_action,
    transcript: ingest.transcript || event.transcript,
    requestId: ingest.stt?.request_id ?? null,
  };
}
