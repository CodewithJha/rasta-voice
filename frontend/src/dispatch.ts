import type { IngestResult } from "./types";

export function initDispatch(root: HTMLElement): void {
  const slate = document.createElement("section");
  slate.className = "slate";
  slate.setAttribute("aria-labelledby", "dispatch-title");

  const title = document.createElement("h2");
  title.id = "dispatch-title";
  title.textContent = "Dispatch slate";

  const status = document.createElement("p");
  status.textContent = "Dark. No drop has come in on this desk.";

  const list = document.createElement("dl");
  list.hidden = true;

  slate.append(title, status, list);
  root.append(slate);

  window.addEventListener("rasta:event", (event) => {
    const detail = (event as CustomEvent<IngestResult>).detail;
    paint(status, list, detail);
  });
}

function paint(status: HTMLElement, list: HTMLElement, result: IngestResult): void {
  const event = result.event;
  const seconds = result.stt.audio_seconds === null ? "" : ` · ${result.stt.audio_seconds}s audio`;
  status.textContent = `Live Prisma · ${result.stt.model}${seconds}`;
  list.hidden = false;
  list.replaceChildren();
  const rows: Array<[string, string]> = [
    ["intent", event.intent.replaceAll("_", " ")],
    ["order", event.order_id ?? "—"],
    ["eta", event.eta_minutes === null ? "—" : `${event.eta_minutes} min`],
    ["urgency", event.urgency],
    ["do", event.dispatch_action],
  ];
  for (const [term, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }
}
