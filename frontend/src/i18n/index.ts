/** Small en / hi-en catalogue. The passcode is never written here or to storage. */

import { en, type MessageKey } from "./en";
import { hiEn } from "./hi-en";

export type { MessageKey };
export type Locale = "en" | "hi-en";

export const LOCALES: readonly Locale[] = ["en", "hi-en"];
export const DEFAULT_LOCALE: Locale = "hi-en";
export const LOCALE_STORAGE_KEY = "rasta-locale";
export const LOCALE_EVENT = "rasta:locale";

const catalogues: Record<Locale, Record<MessageKey, string>> = {
  en,
  "hi-en": hiEn,
};

let current: Locale = DEFAULT_LOCALE;

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "hi-en";
}

export function documentLang(locale: Locale = current): string {
  return locale === "hi-en" ? "hi" : "en";
}

export function getLocale(): Locale {
  return current;
}

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  const table = catalogues[current];
  let text = table[key] || catalogues.en[key] || key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

export function setLocale(locale: Locale): void {
  current = locale;
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Storage can be blocked; the session still switches.
  }
  if (typeof document !== "undefined") {
    document.documentElement.lang = documentLang(locale);
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
  }
}

export function readStoredLocale(): Locale | undefined {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return isLocale(raw) ? raw : undefined;
  } catch {
    return undefined;
  }
}

export function initLocale(): Locale {
  setLocale(readStoredLocale() ?? DEFAULT_LOCALE);
  return current;
}

export function onLocaleChange(paint: () => void): () => void {
  const listener = (): void => {
    paint();
  };
  window.addEventListener(LOCALE_EVENT, listener);
  return () => window.removeEventListener(LOCALE_EVENT, listener);
}

export function missingHiEnKeys(source: Record<MessageKey, string> = hiEn): MessageKey[] {
  return (Object.keys(en) as MessageKey[]).filter((key) => !source[key]);
}
