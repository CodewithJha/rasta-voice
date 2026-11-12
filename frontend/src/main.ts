import { initDispatch } from "./dispatch";
import { initRider } from "./rider";
import "./styles.css";

const app = document.querySelector("#app");
if (!app) {
  throw new Error("missing #app");
}

app.innerHTML = `
  <p class="wall" aria-hidden="true">Rasta</p>
  <header class="mast">
    <p class="kicker">Night drop · bag 04</p>
    <h1>Rasta Voice</h1>
    <p class="lede">A rider speaks through horns and wind. Dispatch gets the order, not the noise.</p>
  </header>
  <div class="layout">
    <div id="rider-root"></div>
    <div id="dispatch-root"></div>
  </div>
  <p class="colophon">Synthetic clips only. No real phone numbers, calls, or customer records. Speech path is Gnani Prisma, then a dispatch event, then Timbre when the reply issue lands.</p>
`;

const rider = document.querySelector("#rider-root");
const dispatch = document.querySelector("#dispatch-root");
if (!(rider instanceof HTMLElement) || !(dispatch instanceof HTMLElement)) {
  throw new Error("missing roots");
}
initRider(rider);
initDispatch(dispatch);
