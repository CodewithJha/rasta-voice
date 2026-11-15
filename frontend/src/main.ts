import { initDispatch } from "./dispatch";
import { getLocale, initLocale, onLocaleChange, setLocale, t, type Locale } from "./i18n";
import { initRider } from "./rider";
import "./styles.css";

const app = document.querySelector("#app");
if (!app) throw new Error("missing #app");
initLocale();
app.innerHTML = `
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="app-banner" hidden role="status" aria-live="polite"></div>
  <header class="app-header">
    <a class="brand" href="#rider">Rasta Voice</a>
    <nav class="view-nav" aria-label="Workspace">
      <a href="#rider" data-view="rider"></a>
      <a href="#dispatch" data-view="dispatch"></a>
    </nav>
    <div class="locale-toggle" role="group"></div>
  </header>
  <main id="main" class="workspace">
    <div id="rider-root"></div>
    <div id="dispatch-root" hidden></div>
  </main>
  <footer class="colophon"></footer>
`;
const banner = app.querySelector<HTMLElement>(".app-banner")!;
const toggle = app.querySelector<HTMLElement>(".locale-toggle")!;
const colophon = app.querySelector<HTMLElement>(".colophon")!;
const rider = app.querySelector<HTMLElement>("#rider-root")!;
const dispatch = app.querySelector<HTMLElement>("#dispatch-root")!;
const links = Array.from(app.querySelectorAll<HTMLAnchorElement>("[data-view]"));
let currentView = "rider";
let dispatchStarted = false;
const riderController = initRider(rider);

const paintMast = (): void => {
  colophon.textContent = t("colophon");
  toggle.setAttribute("aria-label", t("locale.toggle"));
  for (const button of Array.from(toggle.querySelectorAll("button"))) {
    const locale = button.dataset.locale;
    button.textContent = locale === "en" ? t("locale.en") : t("locale.hi");
    button.setAttribute("aria-pressed", String(locale === getLocale()));
  }
  for (const link of links) link.textContent = t(link.dataset.view === "rider" ? "nav.rider" : "nav.dispatch");
};
for (const locale of ["hi-en", "en"] as Locale[]) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "locale-btn";
  button.dataset.locale = locale;
  button.addEventListener("click", () => setLocale(locale));
  toggle.append(button);
}
paintMast();
onLocaleChange(paintMast);
const showBanner = (message: string): void => {
  banner.replaceChildren();
  const text = document.createElement("p");
  text.textContent = message;
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.textContent = t("banner.dismiss");
  dismiss.addEventListener("click", () => { banner.hidden = true; });
  banner.append(text, dismiss);
  banner.hidden = false;
};
const selectView = (focus = false): void => {
  const next = location.hash === "#dispatch" ? "dispatch" : "rider";
  if (next !== currentView && riderController.isBusy()) {
    history.replaceState(null, "", `#${currentView}`);
    showBanner(t("nav.finishRecording"));
    return;
  }
  currentView = next;
  rider.hidden = next !== "rider";
  dispatch.hidden = next !== "dispatch";
  const alreadyStarted = dispatchStarted;
  if (next === "dispatch" && !dispatchStarted) {
    dispatchStarted = true;
    initDispatch(dispatch);
  }
  for (const link of links) {
    if (link.dataset.view === next) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (alreadyStarted) window.dispatchEvent(new CustomEvent("rasta:view", { detail: next }));
  if (focus) (next === "rider" ? rider : dispatch).querySelector<HTMLElement>("h1, h2")?.focus();
};
window.addEventListener("hashchange", () => selectView(true));
selectView();
window.addEventListener("error", (event) => {
  event.preventDefault();
  showBanner(event.message || t("banner.runtime"));
});
window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  const reason: unknown = event.reason;
  showBanner(reason instanceof Error ? reason.message : t("banner.runtime"));
});
window.addEventListener("offline", () => showBanner(t("error.offline")));
