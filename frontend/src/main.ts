import { initDispatch } from "./dispatch";
import { getLocale, initLocale, onLocaleChange, setLocale, t, type Locale } from "./i18n";
import { initRider } from "./rider";
import "./styles.css";

const app = document.querySelector("#app");
if (!app) {
  throw new Error("missing #app");
}

initLocale();

app.innerHTML = `
  <div class="app-banner" hidden role="status" aria-live="polite"></div>
  <p class="wall" aria-hidden="true">Rasta</p>
  <header class="mast">
    <div class="mast-row">
      <p class="kicker" data-i18n="mast.kicker"></p>
      <div class="locale-toggle" role="group" data-i18n-aria="locale.toggle"></div>
    </div>
    <h1>Rasta Voice</h1>
    <p class="lede" data-i18n="mast.lede"></p>
  </header>
  <div class="layout">
    <div id="rider-root"></div>
    <div id="dispatch-root"></div>
  </div>
  <p class="colophon" data-i18n="colophon"></p>
`;

const banner = app.querySelector(".app-banner");
const toggle = app.querySelector(".locale-toggle");
const kicker = app.querySelector(".kicker");
const lede = app.querySelector(".lede");
const colophon = app.querySelector(".colophon");
const rider = document.querySelector("#rider-root");
const dispatch = document.querySelector("#dispatch-root");
if (
  !(banner instanceof HTMLElement) ||
  !(toggle instanceof HTMLElement) ||
  !(kicker instanceof HTMLElement) ||
  !(lede instanceof HTMLElement) ||
  !(colophon instanceof HTMLElement) ||
  !(rider instanceof HTMLElement) ||
  !(dispatch instanceof HTMLElement)
) {
  throw new Error("missing roots");
}

const paintMast = (): void => {
  kicker.textContent = t("mast.kicker");
  lede.textContent = t("mast.lede");
  colophon.textContent = t("colophon");
  toggle.setAttribute("aria-label", t("locale.toggle"));
  for (const button of Array.from(toggle.querySelectorAll("button"))) {
    const locale = button.getAttribute("data-locale");
    if (locale === "en" || locale === "hi-en") {
      button.textContent = locale === "en" ? t("locale.en") : t("locale.hi");
      button.setAttribute("aria-pressed", String(locale === getLocale()));
    }
  }
};

const addLocaleButton = (locale: Locale): void => {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "locale-btn";
  button.dataset.locale = locale;
  button.addEventListener("click", () => {
    setLocale(locale);
  });
  toggle.append(button);
};

addLocaleButton("hi-en");
addLocaleButton("en");
paintMast();
onLocaleChange(paintMast);

const showBanner = (message: string): void => {
  banner.replaceChildren();
  const text = document.createElement("p");
  text.textContent = message;
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.textContent = t("banner.dismiss");
  dismiss.addEventListener("click", () => {
    banner.hidden = true;
    banner.replaceChildren();
  });
  banner.append(text, dismiss);
  banner.hidden = false;
};

window.addEventListener("error", (event) => {
  event.preventDefault();
  showBanner(event.message || t("banner.runtime"));
});
window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  const reason = event.reason;
  const message =
    reason instanceof Error ? reason.message : typeof reason === "string" ? reason : t("banner.runtime");
  showBanner(message || t("banner.runtime"));
});
window.addEventListener("offline", () => {
  showBanner(t("error.offline"));
});

initRider(rider);
initDispatch(dispatch);
