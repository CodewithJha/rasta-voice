import { t, type MessageKey } from "./i18n";

export function deskNeedsUnlock(status: number): boolean {
  return status === 401 || status === 503;
}

export function describeDeskError(status: number): string {
  const key = deskErrorKey(status);
  if (key === "desk.failed") {
    return t(key, { status });
  }
  return t(key);
}

export function deskErrorKey(status: number): MessageKey {
  if (status === 401) return "desk.unlockCopy";
  if (status === 404) return "desk.notUp";
  if (status === 429) return "desk.rateLimit";
  if (status === 503) return "desk.passcodeUnset";
  if (status === 502) return "desk.upstream";
  if (status === 0) return "desk.network";
  return "desk.failed";
}
