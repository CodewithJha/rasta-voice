import { t } from "./i18n";

/** Map HTTP failures to named chrome. Transcripts are never rewritten here. */

export function describeError(status: number, text: string): string {
  const detail = parseDetail(text);
  const upstream = detail && typeof detail === "object" ? readUpstream(detail) : undefined;
  const message = typeof detail === "string" ? detail : readErrorMessage(detail);
  if (status === 429) {
    return t("error.rate");
  }
  if (status === 402 || upstream === 402) {
    return t("error.credit");
  }
  if (status === 503) {
    return describeUnavailable(message);
  }
  if (status === 502) {
    const extra = upstream != null ? ` (upstream ${upstream})` : "";
    return message ? `${t("error.upstream")}${extra}. ${message}` : `${t("error.upstream")}${extra}.`;
  }
  return message ? `${status}: ${message}` : `${status}: ${text}`;
}

export function describeUnavailable(message: string | undefined): string {
  const lower = (message ?? "").toLowerCase();
  if (/paus/.test(lower)) return t("error.paused");
  if (/budget|exhaust/.test(lower)) return t("error.budget");
  if (/busy|concurrency/.test(lower)) return t("error.busy");
  if (/key/.test(lower) || !message) return t("error.missingKey");
  return message;
}

export function describeNetworkError(err: unknown): string {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return t("error.offline");
  }
  if (err instanceof DOMException && err.name === "AbortError") {
    return t("error.timeout");
  }
  return err instanceof Error ? err.message : t("error.network");
}

export function parseDetail(text: string): unknown {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "error" in parsed) {
      return (parsed as { error: unknown }).error;
    }
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
  if (!detail || typeof detail !== "object") return undefined;
  if ("message" in detail && typeof (detail as { message: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  if ("error" in detail) {
    const error = (detail as { error: unknown }).error;
    if (typeof error === "string") return error;
  }
  return undefined;
}
