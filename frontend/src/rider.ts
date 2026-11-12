import type { IngestResult } from "./types";

export function initRider(root: HTMLElement): void {
  const chit = document.createElement("section");
  chit.className = "chit";
  chit.setAttribute("aria-labelledby", "rider-title");

  const sticker = document.createElement("p");
  sticker.className = "sticker";
  sticker.textContent = "8 kHz line";

  const title = document.createElement("h2");
  title.id = "rider-title";
  title.textContent = "What the rider shouted over the horns";

  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent =
    "Upload a short clip (30 s max), or let Timbre speak a synthetic rider line. Both are real Gnani Prisma calls.";

  const form = document.createElement("form");
  const row = document.createElement("div");
  row.className = "row";

  const fileLabel = document.createElement("label");
  fileLabel.className = "file";
  fileLabel.textContent = "Choose a clip";
  const file = document.createElement("input");
  file.type = "file";
  file.accept = "audio/*,.wav,.mp3,.ogg,.flac,.m4a";
  file.name = "audio_file";
  fileLabel.append(file);

  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = "Send up the line";

  const sample = document.createElement("button");
  sample.type = "button";
  sample.className = "ghost";
  sample.textContent = "Speak a sample line";

  row.append(fileLabel, send, sample);
  form.append(row);

  const out = document.createElement("pre");
  out.tabIndex = 0;
  out.textContent = "Waiting for a clip.";

  const fine = document.createElement("p");
  fine.className = "fine";
  fine.textContent = "Timbre v3.0 → Prisma v3.0 REST · transliterate · Hindi and English hints. No real phone numbers.";

  chit.append(sticker, title, hint, form, out, fine);
  root.append(chit);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const picked = file.files?.[0];
    if (!picked) {
      out.textContent = "Pick a clip first, or speak a sample line.";
      return;
    }
    const body = new FormData();
    body.append("audio_file", picked, picked.name);
    void post("/api/ingest", { method: "POST", body }, out);
  });

  sample.addEventListener("click", () => {
    void post("/api/ingest/sample", { method: "POST" }, out);
  });
}

async function post(url: string, init: RequestInit, out: HTMLElement): Promise<void> {
  out.textContent = "On the line…";
  try {
    const response = await fetch(url, init);
    const text = await response.text();
    if (!response.ok) {
      out.textContent = "";
      const err = document.createElement("span");
      err.className = "err";
      err.textContent = `${response.status} ${text}`;
      out.append(err);
      return;
    }
    const result = JSON.parse(text) as IngestResult;
    out.textContent = JSON.stringify(result, null, 2);
    window.dispatchEvent(new CustomEvent<IngestResult>("rasta:event", { detail: result }));
  } catch (err) {
    out.textContent = err instanceof Error ? err.message : "Request failed";
  }
}
