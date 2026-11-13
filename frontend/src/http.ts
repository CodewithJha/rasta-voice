/** Shared 20 s abort for every browser fetch. Callers must not auto-retry POSTs.

The deadline covers header arrival and body consumption. A stalled body is
cancelled rather than left pending after a 20 s header-only timeout.
*/

export const FETCH_TIMEOUT_MS = 20_000;

export interface TimedResponse {
  response: Response;
  text: string;
}

export async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs: number = FETCH_TIMEOUT_MS,
): Promise<TimedResponse> {
  const controller = new AbortController();
  let response: Response | undefined;
  const cancelBody = (): void => {
    const body = response?.body;
    if (!body) return;
    try {
      void body.cancel().catch(() => undefined);
    } catch {
      // Already locked or closed by the pending text() reader.
    }
  };
  const timer = setTimeout(() => {
    controller.abort();
    cancelBody();
  }, timeoutMs);
  const parent = init.signal;
  const onParentAbort = (): void => {
    controller.abort();
    cancelBody();
  };
  if (parent) {
    if (parent.aborted) {
      onParentAbort();
    } else {
      parent.addEventListener("abort", onParentAbort, { once: true });
    }
  }
  try {
    response = await fetch(url, { ...init, signal: controller.signal });
    const text = await response.text();
    return { response, text };
  } finally {
    clearTimeout(timer);
    if (parent) {
      parent.removeEventListener("abort", onParentAbort);
    }
  }
}
