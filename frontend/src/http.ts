/** Shared 20 s abort for every browser fetch. Callers must not auto-retry POSTs. */

export const FETCH_TIMEOUT_MS = 20_000;

export async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs: number = FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const parent = init.signal;
    if (parent) {
      if (parent.aborted) {
        controller.abort();
      } else {
        parent.addEventListener("abort", () => controller.abort(), { once: true });
      }
    }
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}
