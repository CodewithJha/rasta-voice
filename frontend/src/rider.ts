import { fillChitResult } from "./chit-view";
import { describeError, describeNetworkError } from "./errors";
import { fetchWithTimeout } from "./http";
import { onLocaleChange, t } from "./i18n";
import { renderReplyConfirmation, setWavAudio, type ReplyPayload } from "./reply-view";
import type { IngestResult } from "./types";
import "./rider.css";

const TARGET_RATE = 16_000;
const FRAME_BYTES = 1024;
const SAMPLES_PER_FRAME = FRAME_BYTES / 2;

type LineCondition = "clean" | "noisy";

interface SimulateEnvelope {
  condition: LineCondition;
  audio_base64: string;
  ingest: IngestResult;
}

// Live-mic dirt would be a horn buffer summed in this worklet, not a second
// server mix. This issue ships the upload / REST sample path as the demo
// dirt; Talk and Stream a sample line stay a clean mic.

export function initRider(root: HTMLElement): void {
  const chit = document.createElement("section");
  chit.className = "chit";
  chit.setAttribute("aria-labelledby", "rider-title");

  const sticker = document.createElement("p");
  sticker.className = "sticker";
  sticker.textContent = t("rider.sticker");

  const title = document.createElement("h2");
  title.id = "rider-title";
  title.textContent = t("rider.title");

  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent = t("rider.hint");

  const mix = document.createElement("div");
  mix.className = "rider-mix";
  mix.setAttribute("role", "radiogroup");
  mix.setAttribute("aria-label", t("rider.mixGroup"));

  const mixLabel = document.createElement("p");
  mixLabel.className = "rider-mix-label";
  mixLabel.id = "rider-mix-hint";
  mixLabel.textContent = t("rider.mixLabel");

  const switchRow = document.createElement("div");
  switchRow.className = "rider-mix-switch";

  const cleanBtn = document.createElement("button");
  cleanBtn.type = "button";
  cleanBtn.textContent = t("rider.clean");
  cleanBtn.setAttribute("role", "radio");
  cleanBtn.setAttribute("aria-label", t("rider.clean"));

  const noisyBtn = document.createElement("button");
  noisyBtn.type = "button";
  noisyBtn.textContent = t("rider.noisy");
  noisyBtn.setAttribute("role", "radio");
  noisyBtn.setAttribute("aria-label", t("rider.noisy"));

  switchRow.append(cleanBtn, noisyBtn);
  mix.append(mixLabel, switchRow);

  const form = document.createElement("form");
  const row = document.createElement("div");
  row.className = "row";

  const fileLabel = document.createElement("label");
  fileLabel.className = "file";
  fileLabel.textContent = t("rider.chooseClip");
  const file = document.createElement("input");
  file.type = "file";
  file.accept = "audio/*,.wav,.mp3,.ogg,.flac,.m4a";
  file.name = "audio_file";
  fileLabel.append(file);

  const send = document.createElement("button");
  send.type = "submit";
  send.textContent = t("rider.send");

  const restSample = document.createElement("button");
  restSample.type = "button";
  restSample.className = "ghost";
  restSample.textContent = t("rider.sample");

  row.append(fileLabel, send, restSample);
  form.append(row);

  const live = document.createElement("div");
  live.className = "rider-live";

  const talk = document.createElement("button");
  talk.type = "button";
  talk.className = "talk";
  talk.textContent = t("rider.talk");
  talk.setAttribute("aria-pressed", "false");

  const streamSample = document.createElement("button");
  streamSample.type = "button";
  streamSample.className = "ghost";
  streamSample.textContent = t("rider.streamSample");

  live.append(talk, streamSample);

  const micHint = document.createElement("p");
  micHint.className = "rider-mic-hint";
  micHint.hidden = true;

  const out = document.createElement("div");
  out.className = "chit-out";
  out.tabIndex = 0;
  out.dataset.mode = "waiting";
  out.textContent = t("rider.waiting");

  const players = document.createElement("div");
  players.className = "rider-players";

  const clipPlayer = document.createElement("div");
  clipPlayer.className = "rider-player";
  const clipCaption = document.createElement("p");
  clipCaption.textContent = t("rider.whatPrismaHeard");
  const clipAudio = document.createElement("audio");
  clipAudio.controls = true;
  clipAudio.hidden = true;
  clipPlayer.append(clipCaption, clipAudio);

  const replyPlayer = document.createElement("div");
  replyPlayer.className = "rider-player";
  const hear = document.createElement("button");
  hear.type = "button";
  hear.className = "ghost";
  hear.textContent = t("rider.hearDispatch");
  hear.setAttribute("aria-label", t("rider.hearDispatch"));
  hear.disabled = true;
  const replyCaption = document.createElement("p");
  replyCaption.textContent = t("rider.timbreCaption");
  const replyText = document.createElement("p");
  replyText.className = "rider-reply-text";
  replyText.hidden = true;
  const replyAudio = document.createElement("audio");
  replyAudio.controls = true;
  replyAudio.hidden = true;
  replyPlayer.append(hear, replyCaption, replyText, replyAudio);

  players.append(clipPlayer, replyPlayer);

  const fine = document.createElement("p");
  fine.className = "fine";
  fine.textContent = t("rider.fine");

  chit.append(sticker, title, hint, mix, form, live, micHint, out, players, fine);
  root.append(chit);

  let condition: LineCondition = "clean";
  let lastEventId: string | undefined;
  let lastShown: IngestResult | undefined;
  let busy = false;

  const applyCondition = (value: LineCondition): void => {
    condition = value;
    cleanBtn.setAttribute("aria-checked", String(value === "clean"));
    noisyBtn.setAttribute("aria-checked", String(value === "noisy"));
    cleanBtn.tabIndex = value === "clean" ? 0 : -1;
    noisyBtn.tabIndex = value === "noisy" ? 0 : -1;
  };
  applyCondition("clean");

  const focusCurrent = (): void => {
    (condition === "clean" ? cleanBtn : noisyBtn).focus();
  };

  for (const button of [cleanBtn, noisyBtn]) {
    button.addEventListener("click", () => {
      applyCondition(button === noisyBtn ? "noisy" : "clean");
    });
    button.addEventListener("keydown", (event) => {
      if (
        event.key === "ArrowRight" ||
        event.key === "ArrowLeft" ||
        event.key === "ArrowUp" ||
        event.key === "ArrowDown"
      ) {
        event.preventDefault();
        applyCondition(condition === "clean" ? "noisy" : "clean");
        focusCurrent();
      }
    });
  }

  const mic = new MicSession(out, talk, live, () => setBusy(false), rememberIngest);

  const setBusy = (value: boolean): void => {
    busy = value;
    send.disabled = value;
    restSample.disabled = value;
    streamSample.disabled = value;
    talk.disabled = value && !mic.recording;
    hear.disabled = value || !lastEventId;
  };

  function rememberIngest(ingest: IngestResult): void {
    lastEventId = ingest.id;
    lastShown = ingest;
    hear.disabled = busy || !lastEventId;
  }

  const refreshMicHint = (): void => {
    if (typeof window === "undefined") {
      return;
    }
    if (!window.isSecureContext) {
      micHint.hidden = false;
      micHint.textContent = t("rider.insecure");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      micHint.hidden = false;
      micHint.textContent = t("rider.micMissing");
      return;
    }
    if (!micHint.dataset.blocked) {
      micHint.hidden = true;
      micHint.textContent = "";
    } else {
      micHint.hidden = false;
      micHint.textContent = t("rider.micBlocked");
    }
  };

  const paintLabels = (): void => {
    sticker.textContent = t("rider.sticker");
    title.textContent = t("rider.title");
    hint.textContent = t("rider.hint");
    mix.setAttribute("aria-label", t("rider.mixGroup"));
    mixLabel.textContent = t("rider.mixLabel");
    cleanBtn.textContent = t("rider.clean");
    cleanBtn.setAttribute("aria-label", t("rider.clean"));
    noisyBtn.textContent = t("rider.noisy");
    noisyBtn.setAttribute("aria-label", t("rider.noisy"));
    // Keep the visible name on the file control; the input stays labelled by the parent.
    const fileName = file.files?.[0]?.name;
    fileLabel.textContent = t("rider.chooseClip");
    fileLabel.append(file);
    if (fileName) {
      const picked = document.createElement("span");
      picked.className = "file-name";
      picked.textContent = ` ${fileName}`;
      fileLabel.append(picked);
    }
    if (!busy) {
      send.textContent = t("rider.send");
      restSample.textContent = t("rider.sample");
      streamSample.textContent = t("rider.streamSample");
    } else {
      send.textContent = t("rider.onTheLine");
      restSample.textContent = t("rider.onTheLine");
      streamSample.textContent = t("rider.onTheLine");
    }
    if (mic.recording) {
      talk.textContent = t("rider.stop");
    } else if (!busy) {
      talk.textContent = t("rider.talk");
    }
    hear.textContent = t("rider.hearDispatch");
    hear.setAttribute("aria-label", t("rider.hearDispatch"));
    clipCaption.textContent = t("rider.whatPrismaHeard");
    replyCaption.textContent = t("rider.timbreCaption");
    fine.textContent = t("rider.fine");
    const mode = out.dataset.mode ?? "waiting";
    if (mode === "result" && lastShown) {
      fillChitResult(out, lastShown);
    } else if (mode === "waiting") {
      out.textContent = t("rider.waiting");
    } else if (mode === "pending") {
      out.textContent = t("rider.onTheLine");
    } else if (mode === "listening") {
      out.textContent = t("rider.listening");
    } else if (mode === "pick") {
      out.dataset.mode = "pick";
      out.textContent = t("rider.pickFirst");
    }
    refreshMicHint();
  };

  paintLabels();
  onLocaleChange(paintLabels);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (busy || mic.recording) return;
    const picked = file.files?.[0];
    if (!picked) {
      out.dataset.mode = "pick";
      out.textContent = t("rider.pickFirst");
      return;
    }
    const body = new FormData();
    body.append("audio_file", picked, picked.name);
    void withBusy(send, () =>
      post(`/api/simulate?condition=${condition}`, { method: "POST", body }, out, {
        onIngest: rememberIngest,
        clipAudio,
      }),
    );
  });

  restSample.addEventListener("click", () => {
    if (busy || mic.recording) return;
    void withBusy(restSample, () =>
      post(`/api/ingest/sample?condition=${condition}`, { method: "POST" }, out, {
        onIngest: rememberIngest,
        clipAudio,
      }),
    );
  });

  talk.addEventListener("click", () => {
    if (mic.recording) {
      mic.stop();
      return;
    }
    if (busy) return;
    setBusy(true);
    void mic.start();
  });

  streamSample.addEventListener("click", () => {
    if (busy || mic.recording) return;
    setBusy(true);
    live.dataset.state = "live";
    out.dataset.mode = "pending";
    out.textContent = t("rider.onTheLine");
    clipAudio.removeAttribute("src");
    clipAudio.hidden = true;
    void openStream(out, { type: "sample" }, rememberIngest).finally(() => {
      delete live.dataset.state;
      setBusy(false);
    });
  });

  hear.addEventListener("click", () => {
    if (busy || !lastEventId) return;
    void withBusy(hear, () => postReply(`/api/reply/${lastEventId}`, out, replyAudio, replyText));
  });

  async function withBusy(button: HTMLButtonElement, work: () => Promise<void>): Promise<void> {
    if (busy) return;
    const label = button.textContent;
    setBusy(true);
    button.textContent = t("rider.onTheLine");
    try {
      await work();
    } finally {
      button.textContent = label;
      setBusy(false);
    }
  }
}

class MicSession {
  recording = false;
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private worklet: AudioWorkletNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private mute: GainNode | null = null;
  private socket: WebSocket | null = null;
  private packer: PcmPacker | null = null;

  constructor(
    private readonly out: HTMLElement,
    private readonly talk: HTMLButtonElement,
    private readonly live: HTMLElement,
    private readonly onDone: () => void,
    private readonly onIngest: (ingest: IngestResult) => void,
  ) {}

  async start(): Promise<void> {
    if (!window.isSecureContext) {
      this.out.dataset.mode = "error";
      this.out.textContent = t("rider.insecure");
      this.onDone();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      this.out.dataset.mode = "error";
      this.out.textContent = t("rider.micMissing");
      this.onDone();
      return;
    }
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true },
        video: false,
      });
    } catch {
      this.out.dataset.mode = "error";
      this.out.textContent = t("rider.micBlocked");
      this.onDone();
      return;
    }
    this.stream = media;
    this.out.dataset.mode = "listening";
    this.out.textContent = t("rider.listening");
    const context = new AudioContext();
    this.context = context;
    if (context.state === "suspended") {
      await context.resume();
    }
    this.packer = new PcmPacker(context.sampleRate, TARGET_RATE, (frame) => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(frame);
      }
    });
    this.source = context.createMediaStreamSource(media);
    const hooked = await this.attachWorklet(context, this.packer);
    if (!hooked) {
      this.attachScriptProcessor(context, this.packer);
    }
    this.socket = connectStream(this.out, () => this.teardown(false), this.onDone, this.onIngest);
    this.recording = true;
    this.live.dataset.state = "live";
    this.talk.disabled = false;
    this.talk.textContent = t("rider.stop");
    this.talk.setAttribute("aria-pressed", "true");
  }

  stop(): void {
    this.packer?.flush();
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "commit", sample_rate: TARGET_RATE }));
    }
    this.teardown(true);
  }

  private async attachWorklet(context: AudioContext, packer: PcmPacker): Promise<boolean> {
    try {
      await context.audioWorklet.addModule("/pcm-worklet.js");
    } catch {
      return false;
    }
    const worklet = new AudioWorkletNode(context, "rasta-pcm");
    worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
      packer.push(event.data);
    };
    this.mute = context.createGain();
    this.mute.gain.value = 0;
    this.source?.connect(worklet);
    worklet.connect(this.mute);
    this.mute.connect(context.destination);
    this.worklet = worklet;
    return true;
  }

  private attachScriptProcessor(context: AudioContext, packer: PcmPacker): void {
    const processor = context.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      packer.push(event.inputBuffer.getChannelData(0));
    };
    this.source?.connect(processor);
    processor.connect(context.destination);
    this.processor = processor;
  }

  private teardown(keepSocket: boolean): void {
    this.recording = false;
    this.talk.textContent = t("rider.talk");
    this.talk.setAttribute("aria-pressed", "false");
    delete this.live.dataset.state;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    try {
      this.source?.disconnect();
      this.worklet?.disconnect();
      this.processor?.disconnect();
      this.mute?.disconnect();
    } catch {
      // already disconnected
    }
    this.source = null;
    this.worklet = null;
    this.processor = null;
    this.mute = null;
    if (this.context) {
      void this.context.close();
      this.context = null;
    }
    if (!keepSocket && this.socket && this.socket.readyState < WebSocket.CLOSING) {
      this.socket.close();
    }
    if (!keepSocket) {
      this.socket = null;
    }
  }
}

class PcmPacker {
  private pending = new Float32Array(0);

  constructor(
    private readonly inRate: number,
    private readonly outRate: number,
    private readonly onFrame: (frame: ArrayBufferLike) => void,
  ) {}

  push(input: Float32Array): void {
    const resampled = resampleLinear(input, this.inRate, this.outRate);
    const merged = new Float32Array(this.pending.length + resampled.length);
    merged.set(this.pending);
    merged.set(resampled, this.pending.length);
    let offset = 0;
    while (offset + SAMPLES_PER_FRAME <= merged.length) {
      this.emit(merged.subarray(offset, offset + SAMPLES_PER_FRAME));
      offset += SAMPLES_PER_FRAME;
    }
    this.pending = merged.slice(offset);
  }

  flush(): void {
    if (this.pending.length === 0) {
      return;
    }
    const padded = new Float32Array(SAMPLES_PER_FRAME);
    padded.set(this.pending.subarray(0, Math.min(this.pending.length, SAMPLES_PER_FRAME)));
    this.emit(padded);
    this.pending = new Float32Array(0);
  }

  private emit(samples: Float32Array): void {
    const int16 = floatToInt16(samples);
    this.onFrame(int16.buffer.slice(int16.byteOffset, int16.byteOffset + int16.byteLength));
  }
}

function resampleLinear(input: Float32Array, inRate: number, outRate: number): Float32Array {
  if (inRate === outRate) {
    return input;
  }
  const outLength = Math.round((input.length * outRate) / inRate);
  const out = new Float32Array(outLength);
  const ratio = inRate / outRate;
  for (let i = 0; i < outLength; i++) {
    const src = i * ratio;
    const index = Math.floor(src);
    const next = Math.min(index + 1, input.length - 1);
    const frac = src - index;
    out[i] = input[index] + (input[next] - input[index]) * frac;
  }
  return out;
}

function floatToInt16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const sample = Math.max(-1, Math.min(1, input[i] ?? 0));
    out[i] = sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff);
  }
  return out;
}

function streamUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/stream`;
}

function openStream(
  out: HTMLElement,
  first: { type: string },
  onIngest?: (ingest: IngestResult) => void,
): Promise<void> {
  return new Promise((resolve) => {
    const socket = connectStream(out, () => undefined, resolve, onIngest);
    socket.addEventListener("open", () => {
      socket.send(JSON.stringify(first));
    });
  });
}

function connectStream(
  out: HTMLElement,
  onCloseEarly: () => void,
  onDone: () => void,
  onIngest?: (ingest: IngestResult) => void,
): WebSocket {
  const socket = new WebSocket(streamUrl());
  let settled = false;
  const finish = (): void => {
    if (settled) return;
    settled = true;
    onDone();
  };
  socket.addEventListener("message", (event) => {
    if (typeof event.data !== "string") return;
    let frame: { type?: string; text?: string; message?: string } & Partial<IngestResult>;
    try {
      frame = JSON.parse(event.data) as typeof frame;
    } catch {
      return;
    }
    if (frame.type === "ping") return;
    if (frame.type === "transcript" && frame.text) {
      out.textContent = frame.text;
      return;
    }
    if (frame.type === "error") {
      out.dataset.mode = "error";
      out.textContent = frame.message ?? t("error.stream");
      return;
    }
    if (frame.type === "event") {
      const { type: _type, ...result } = frame;
      void _type;
      const ingest = result as IngestResult;
      out.dataset.mode = "result";
      fillChitResult(out, ingest);
      onIngest?.(ingest);
      window.dispatchEvent(new CustomEvent<IngestResult>("rasta:event", { detail: ingest }));
    }
  });
  socket.addEventListener("error", () => {
    if (
      out.textContent === t("rider.listening") ||
      out.textContent === t("rider.onTheLine") ||
      out.textContent?.startsWith("Listening") ||
      out.textContent === "On the line…"
    ) {
      out.dataset.mode = "error";
      out.textContent = t("error.streamFailed");
    }
    onCloseEarly();
    finish();
  });
  socket.addEventListener("close", () => {
    onCloseEarly();
    finish();
  });
  return socket;
}

function idempotencyHeaders(init: RequestInit = {}): Headers {
  const headers = new Headers(init.headers);
  if (!headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", crypto.randomUUID());
  }
  return headers;
}

async function post(
  url: string,
  init: RequestInit,
  out: HTMLElement,
  opts: { onIngest: (ingest: IngestResult) => void; clipAudio: HTMLAudioElement },
): Promise<void> {
  out.dataset.mode = "pending";
  out.textContent = t("rider.onTheLine");
  try {
    const { response, text } = await fetchWithTimeout(url, { ...init, headers: idempotencyHeaders(init) });
    if (!response.ok) {
      showError(out, response.status, text);
      return;
    }
    const parsed: unknown = JSON.parse(text);
    const ingest = unwrapIngest(parsed);
    const clip = clipAudioFrom(parsed);
    out.dataset.mode = "result";
    fillChitResult(out, ingest);
    opts.onIngest(ingest);
    if (clip) {
      setAudio(opts.clipAudio, clip);
    } else {
      opts.clipAudio.removeAttribute("src");
      opts.clipAudio.hidden = true;
    }
    window.dispatchEvent(new CustomEvent<IngestResult>("rasta:event", { detail: ingest }));
  } catch (err) {
    out.dataset.mode = "error";
    out.textContent = describeNetworkError(err);
  }
}

async function postReply(
  url: string,
  out: HTMLElement,
  player: HTMLAudioElement,
  textEl: HTMLElement,
): Promise<void> {
  try {
    const { response, text } = await fetchWithTimeout(url, { method: "POST", headers: idempotencyHeaders() });
    if (!response.ok) {
      showError(out, response.status, text);
      return;
    }
    renderReplyConfirmation(JSON.parse(text) as ReplyPayload, player, textEl);
  } catch (err) {
    out.dataset.mode = "error";
    out.textContent = describeNetworkError(err);
  }
}

function setAudio(player: HTMLAudioElement, audioBase64: string): void {
  setWavAudio(player, audioBase64);
}

function unwrapIngest(parsed: unknown): IngestResult {
  if (isEnvelope(parsed)) {
    return parsed.ingest;
  }
  return parsed as IngestResult;
}

function clipAudioFrom(parsed: unknown): string | undefined {
  return isEnvelope(parsed) ? parsed.audio_base64 : undefined;
}

function isEnvelope(value: unknown): value is SimulateEnvelope {
  if (!value || typeof value !== "object") return false;
  const body = value as Partial<SimulateEnvelope>;
  return (
    (body.condition === "clean" || body.condition === "noisy") &&
    typeof body.audio_base64 === "string" &&
    typeof body.ingest === "object" &&
    body.ingest !== null
  );
}

function showError(out: HTMLElement, status: number, text: string): void {
  out.dataset.mode = "error";
  out.replaceChildren();
  const err = document.createElement("span");
  err.className = "err";
  err.textContent = describeError(status, text);
  out.append(err);
}
