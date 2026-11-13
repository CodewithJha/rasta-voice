import type { IngestResult } from "./types";
import "./rider.css";

const TARGET_RATE = 16_000;
const FRAME_BYTES = 1024;
const SAMPLES_PER_FRAME = FRAME_BYTES / 2;
const FETCH_TIMEOUT_MS = 20_000;

type LineCondition = "clean" | "noisy";

interface SimulateEnvelope {
  condition: LineCondition;
  audio_base64: string;
  ingest: IngestResult;
}

interface ReplyPayload {
  text?: string;
  audio_base64?: string;
}

// Live-mic dirt would be a horn buffer summed in this worklet, not a second
// server mix. This issue ships the upload / REST sample path as the demo
// dirt; Talk and Stream a sample line stay a clean mic.
const WORKLET_SRC = `
class RastaPcm extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      this.port.postMessage(channel);
    }
    return true;
  }
}
registerProcessor("rasta-pcm", RastaPcm);
`;

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
    "Talk into the mic (Prisma hears you live), stream a synthetic Timbre line, or upload a short clip. The key stays on the server.";

  const mix = document.createElement("div");
  mix.className = "rider-mix";
  mix.setAttribute("role", "radiogroup");
  mix.setAttribute("aria-label", "Line condition");

  const mixLabel = document.createElement("p");
  mixLabel.className = "rider-mix-label";
  mixLabel.id = "rider-mix-hint";
  mixLabel.textContent =
    "Demo dirt. The scored mixes are in the benchmark. Talk and the live sample stream stay a clean mic.";

  const switchRow = document.createElement("div");
  switchRow.className = "rider-mix-switch";

  const cleanBtn = document.createElement("button");
  cleanBtn.type = "button";
  cleanBtn.textContent = "Clean line";
  cleanBtn.setAttribute("role", "radio");
  cleanBtn.setAttribute("aria-label", "Clean line");

  const noisyBtn = document.createElement("button");
  noisyBtn.type = "button";
  noisyBtn.textContent = "Noisy line";
  noisyBtn.setAttribute("role", "radio");
  noisyBtn.setAttribute("aria-label", "Noisy line");

  switchRow.append(cleanBtn, noisyBtn);
  mix.append(mixLabel, switchRow);

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

  const restSample = document.createElement("button");
  restSample.type = "button";
  restSample.className = "ghost";
  restSample.textContent = "Speak a sample line";

  row.append(fileLabel, send, restSample);
  form.append(row);

  const live = document.createElement("div");
  live.className = "rider-live";

  const talk = document.createElement("button");
  talk.type = "button";
  talk.className = "talk";
  talk.textContent = "Talk";
  talk.setAttribute("aria-pressed", "false");

  const streamSample = document.createElement("button");
  streamSample.type = "button";
  streamSample.className = "ghost";
  streamSample.textContent = "Stream a sample line";

  live.append(talk, streamSample);

  const out = document.createElement("pre");
  out.tabIndex = 0;
  out.textContent = "Waiting for a clip.";

  const players = document.createElement("div");
  players.className = "rider-players";

  const clipPlayer = document.createElement("div");
  clipPlayer.className = "rider-player";
  const clipCaption = document.createElement("p");
  clipCaption.textContent = "What Prisma heard";
  const clipAudio = document.createElement("audio");
  clipAudio.controls = true;
  clipAudio.hidden = true;
  clipPlayer.append(clipCaption, clipAudio);

  const replyPlayer = document.createElement("div");
  replyPlayer.className = "rider-player";
  const hear = document.createElement("button");
  hear.type = "button";
  hear.className = "ghost";
  hear.textContent = "Hear dispatch";
  hear.setAttribute("aria-label", "Hear dispatch");
  hear.disabled = true;
  const replyCaption = document.createElement("p");
  replyCaption.textContent = "Sun lo — the Timbre confirmation";
  const replyAudio = document.createElement("audio");
  replyAudio.controls = true;
  replyAudio.hidden = true;
  replyPlayer.append(hear, replyCaption, replyAudio);

  players.append(clipPlayer, replyPlayer);

  const fine = document.createElement("p");
  fine.className = "fine";
  fine.textContent =
    "Timbre v3.0 → Prisma v3.0 · /api/stream or REST · transliterate · Hindi and English hints. No real phone numbers.";

  chit.append(sticker, title, hint, mix, form, live, out, players, fine);
  root.append(chit);

  let condition: LineCondition = "clean";
  let lastEventId: string | undefined;
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
    hear.disabled = busy || !lastEventId;
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (busy || mic.recording) return;
    const picked = file.files?.[0];
    if (!picked) {
      out.textContent = "Pick a clip first, or talk / stream a sample line.";
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
    out.textContent = "On the line…";
    clipAudio.removeAttribute("src");
    clipAudio.hidden = true;
    void openStream(out, { type: "sample" }, rememberIngest).finally(() => {
      delete live.dataset.state;
      setBusy(false);
    });
  });

  hear.addEventListener("click", () => {
    if (busy || !lastEventId) return;
    void withBusy(hear, () => postReply(`/api/reply/${lastEventId}`, out, replyAudio));
  });

  async function withBusy(button: HTMLButtonElement, work: () => Promise<void>): Promise<void> {
    if (busy) return;
    const label = button.textContent;
    setBusy(true);
    button.textContent = "On the line…";
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
    if (!navigator.mediaDevices?.getUserMedia) {
      this.out.textContent =
        "This browser cannot open the microphone. Upload a clip or stream a sample line instead.";
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
      this.out.textContent =
        "Microphone access was denied. Upload a clip or stream a sample line instead.";
      this.onDone();
      return;
    }
    this.stream = media;
    this.out.textContent = "Listening… speak, then press Stop.";
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
    this.talk.textContent = "Stop";
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
    const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));
    try {
      await context.audioWorklet.addModule(url);
    } catch {
      URL.revokeObjectURL(url);
      return false;
    }
    URL.revokeObjectURL(url);
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
    this.talk.textContent = "Talk";
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
      out.textContent = frame.message ?? "Stream error";
      return;
    }
    if (frame.type === "event") {
      const { type: _type, ...result } = frame;
      void _type;
      const ingest = result as IngestResult;
      out.textContent = JSON.stringify(ingest, null, 2);
      onIngest?.(ingest);
      window.dispatchEvent(new CustomEvent<IngestResult>("rasta:event", { detail: ingest }));
    }
  });
  socket.addEventListener("error", () => {
    if (out.textContent?.startsWith("Listening") || out.textContent === "On the line…") {
      out.textContent = "Stream connection failed.";
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

async function post(
  url: string,
  init: RequestInit,
  out: HTMLElement,
  opts: { onIngest: (ingest: IngestResult) => void; clipAudio: HTMLAudioElement },
): Promise<void> {
  out.textContent = "On the line…";
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    const text = await response.text();
    if (!response.ok) {
      showError(out, response.status, text);
      return;
    }
    const parsed: unknown = JSON.parse(text);
    const ingest = unwrapIngest(parsed);
    const clip = clipAudioFrom(parsed);
    out.textContent = JSON.stringify(ingest, null, 2);
    opts.onIngest(ingest);
    if (clip) {
      setAudio(opts.clipAudio, clip);
    } else {
      opts.clipAudio.removeAttribute("src");
      opts.clipAudio.hidden = true;
    }
    window.dispatchEvent(new CustomEvent<IngestResult>("rasta:event", { detail: ingest }));
  } catch (err) {
    out.textContent = errorMessage(err);
  } finally {
    window.clearTimeout(timer);
  }
}

async function postReply(url: string, out: HTMLElement, player: HTMLAudioElement): Promise<void> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(url, { method: "POST", signal: controller.signal });
    const text = await response.text();
    if (!response.ok) {
      showError(out, response.status, text);
      return;
    }
    const payload = JSON.parse(text) as ReplyPayload;
    if (!payload.audio_base64) {
      out.textContent = "The reply had no audio.";
      return;
    }
    setAudio(player, payload.audio_base64);
  } catch (err) {
    out.textContent = errorMessage(err);
  } finally {
    window.clearTimeout(timer);
  }
}

function setAudio(player: HTMLAudioElement, audioBase64: string): void {
  player.src = `data:audio/wav;base64,${audioBase64}`;
  player.hidden = false;
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
  out.textContent = "";
  const err = document.createElement("span");
  err.className = "err";
  err.textContent = describeError(status, text);
  out.append(err);
}

function describeError(status: number, text: string): string {
  const detail = parseDetail(text);
  const upstream = detail && typeof detail === "object" ? readUpstream(detail) : undefined;
  if (status === 503) {
    return "The key is not set on the server.";
  }
  if (status === 429) {
    return "The demo is busy, try in a minute.";
  }
  if (status === 402 || upstream === 402) {
    return "Credit is exhausted on the speech service.";
  }
  if (status === 502) {
    const extra = upstream != null ? ` (upstream ${upstream})` : "";
    const message = readErrorMessage(detail);
    return message ? `Upstream failed${extra}. ${message}` : `Upstream failed${extra}.`;
  }
  const message = typeof detail === "string" ? detail : readErrorMessage(detail);
  return message ? `${status}: ${message}` : `${status}: ${text}`;
}

function parseDetail(text: string): unknown {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      return (parsed as { detail: unknown }).detail;
    }
    return parsed;
  } catch {
    return text;
  }
}

function readUpstream(detail: object): number | undefined {
  if ("upstream_status" in detail && typeof (detail as { upstream_status: unknown }).upstream_status === "number") {
    return (detail as { upstream_status: number }).upstream_status;
  }
  return undefined;
}

function readErrorMessage(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    const error = (detail as { error: unknown }).error;
    if (typeof error === "string") return error;
  }
  return undefined;
}

function errorMessage(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "The request timed out. Try again.";
  }
  return err instanceof Error ? err.message : "Request failed";
}
