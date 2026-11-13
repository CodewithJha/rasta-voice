import type { TimedResponse } from "./http";

/** fetchWithTimeout has already consumed response.body under its deadline. */
export function deskCsrfToken({ response, text }: TimedResponse): string {
  if (!response.ok) throw new Error("Desk CSRF challenge unavailable");
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("Desk CSRF challenge unavailable");
  }
  if (!data || typeof data !== "object" || !("csrf_token" in data)
      || typeof data.csrf_token !== "string" || !data.csrf_token) {
    throw new Error("Desk CSRF challenge unavailable");
  }
  return data.csrf_token;
}
