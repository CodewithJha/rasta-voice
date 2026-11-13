export const UNLOCK_COPY = "Unlock the desk to keep polling.";
export const NOT_UP_COPY = "Desk list isn't up";
export const PASSCODE_UNSET_COPY = "Desk passcode isn't set on the server.";
export const UPSTREAM_COPY = "Upstream failed";
export const RATE_LIMIT_COPY = "Desk is rate-limited, polling will retry";

export function deskNeedsUnlock(status: number): boolean {
  return status === 401 || status === 503;
}

export function describeDeskError(status: number): string {
  if (status === 401) return UNLOCK_COPY;
  if (status === 404) return NOT_UP_COPY;
  if (status === 429) return RATE_LIMIT_COPY;
  if (status === 503) return PASSCODE_UNSET_COPY;
  if (status === 502) return UPSTREAM_COPY;
  return `Desk failed (${status}).`;
}
