import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const HERE = dirname(fileURLToPath(import.meta.url));
const ANATOMY = "/Users/priyanshujha/.cursor/skills/anatomy";
const k = await import(join(ANATOMY, "kit/iso-kit.mjs"));
const { kitScript } = await import(join(ANATOMY, "scripts/inline-kit.mjs"));

const theme = process.argv.includes("--light") ? "light" : "dark";
const WIDTH = 640;
const HEIGHT = 400;

// Surface plate
const PLATE = { x: -140, y: -72, w: 286, d: 144, r: 8 };
const PLATE_H = 12;
const FOOT_H = 5;

// Intent dial (extractor)
const DIAL = [48, -8];
const DIAL_R = 22;
const DIAL_Z = 78;
const DIAL_H = 11;
const DIAL_TOP = DIAL_Z + DIAL_H;

// Carriage = ticket magazine with six intent "slugs"
const INTENTS = [
  { id: "unreachable", h: 16 },
  { id: "address", h: 14 },
  { id: "missing", h: 18 },
  { id: "delay", h: 12 },
  { id: "sos", h: 20 },
  { id: "other", h: 10 },
];
const CARRIAGE = { x: -34, y: -28, w: 68, d: 56, r: 3 };
const CARRIAGE_Z = 3;
const CARRIAGE_TOP = 8;
const SLUG_W = 9.2;
const STEP = 10.5;
const TIP_R = 2.4;
const PER_TURN = 22;
const RAIL_FROM = -6;
const RAIL_TO = 118;
const CENTRE = -28 + SLUG_W / 2;
const STOPS = INTENTS.map((_, index) => DIAL[0] - CENTRE - STEP * index);
const REACH = [STOPS[STOPS.length - 1] - 6, STOPS[0] + 6];

// Mic mast (rider speech)
const MIC = [-96, 18];
const MIC_Z = 58;

// Timbre horn
const HORN = [96, 28];

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    [MIC[0] - 12, MIC[1], MIC_Z + 28],
    [DIAL[0] + DIAL_R + 8, 0, DIAL_TOP + 4],
    [HORN[0] + 28, HORN[1], 48],
  ],
  WIDTH,
  HEIGHT,
  { pad: 28, azimuth: 40 },
);

const at = (point) => k.iso(point, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (points) =>
  [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 10);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
  const strip = { x: -118, y: PLATE.y + PLATE.d - 16, w: 246, d: 7, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 4, strip.x + strip.w - 4, 4, 5, strip.y + 0.8, 0.6, [2, 3.6], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(
    D(
      [at([strip.x + 2, strip.y + 3.5, 0.6]), at([strip.x + strip.w - 2, strip.y + 3.5, 0.6])],
      { size: 0.45 },
    ),
  );
  const label = { x: -118, y: PLATE.y + 8, w: 52, d: 22, r: 2 };
  out.push(S(k.slabOf(label, 0, 0.8, P, 4), { tone: "lo" }));
  out.push(L(k.planOutline(k.insetPlan(label, 1.6), 0.8, P), { tone: "faint" }));
  out.push(L(k.lineOnTop([label.x + 4, label.y + 6], [label.x + 40, label.y + 6], 0.8, P), { tone: "lo", free: true }));
  out.push(L(k.lineOnTop([label.x + 4, label.y + 11], [label.x + 34, label.y + 11], 0.8, P), { tone: "lo", free: true }));
  out.push(L(k.lineOnTop([label.x + 4, label.y + 16], [label.x + 28, label.y + 16], 0.8, P), { tone: "lo", free: true }));
  out.push(D([at([label.x + 4, label.y + 4, 0.8]), at([label.x + label.w - 4, label.y + 4, 0.8])], { size: 0.4 }));
  return out.join("");
}

function rails() {
  const out = [];
  for (const y of [-22, 18]) {
    out.push(S(k.slabOf({ x: RAIL_FROM, y, w: RAIL_TO - RAIL_FROM, d: 5, r: 1 }, 0, 3, P, 3, 0.4), { tone: "mid" }));
    out.push(D([RAIL_FROM + 6, RAIL_TO - 6].map((x) => at([x, y + 2.5, 3])), { size: 0.4 }));
  }
  for (const x of [RAIL_FROM - 5, RAIL_TO]) {
    out.push(S(k.slabOf({ x, y: -25, w: 5, d: 50, r: 1.2 }, 0, 7, P, 3, 0.5), { tone: "mid" }));
    out.push(D([at([x + 2.5, -20, 7]), at([x + 2.5, 20, 7])], { size: 0.45 }));
  }
  return out.join("");
}

function mic() {
  const out = [];
  const [x, y] = MIC;
  out.push(S(k.cylinder(x, y, 6, 0, 4, P, 28), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 3.2, 4, MIC_Z - 4, P, 24), { tone: "mid", crease: "none" }));
  out.push(L([20, 40].map((z) => k.sideArc(x, y, 3.2, z, P, 14)).join(""), { tone: "faint" }));
  out.push(S(k.cylinder(x, y, 7, MIC_Z, 5, P, 28), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, 9, MIC_Z + 5, 10, P, 36), { tone: "hi" }));
  out.push(L(k.knurl(x, y, 9, MIC_Z + 5, MIC_Z + 15, 40, P), { tone: "lo" }));
  out.push(L(k.ring(x, y, 6.5, MIC_Z + 15, P, 28), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 3.5, MIC_Z + 15, 6, P, 20), { tone: "hi", lit: true }));
  out.push(L([32, 38, 46].map((z) => k.sideArc(x, y, 4.2, z, P, 16)).join(""), { tone: "lo" }));
  out.push(D([at([x, y, MIC_Z + 21])], { size: 0.55, tone: "hi" }));
  return out.join("");
}

function horn() {
  const out = [];
  const [x, y] = HORN;
  out.push(S(k.cylinder(x, y, 8, 0, 6, P, 28), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 5, 6, 18, P, 28), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, 14, 24, 6, P, 40), { tone: "hi" }));
  out.push(L(k.ring(x, y, 11, 30, P, 40), { tone: "lo" }));
  out.push(L(k.ring(x, y, 7, 30, P, 28), { tone: "faint" }));
  out.push(D([at([x, y, 30])], { size: 0.5 }));
  {
    const route = [
      [x - 10, y - 4, 8],
      [70, 10, 6],
      [DIAL[0] + 18, 8, DIAL_Z - 4],
    ].map(at);
    out.push(
      k.wireSvg(route[0], route[route.length - 1], {
        via: route.slice(1, -1),
        tone: "lo",
        size: 1.1,
      }),
    );
  }
  return out.join("");
}

function dialStand() {
  const out = [];
  const [x, y] = DIAL;
  const mag = { x: x - 22, y: y - 18, w: 40, d: 36, r: 3 };
  out.push(S(k.slabOf(mag, 0, 10, P, 6, 0.8), { tone: "mid" }));
  out.push(D([at([mag.x + 5, mag.y + 5, 10]), at([mag.x + mag.w - 5, mag.y + 5, 10])], { size: 0.45 }));
  out.push(S(k.cylinder(x, y, 3.2, 10, DIAL_Z - 10, P, 24), { tone: "mid", crease: "none" }));
  out.push(L([30, 50].map((z) => k.sideArc(x, y, 3.2, z, P, 12)).join(""), { tone: "faint" }));
  return out.join("");
}

function carriage() {
  const out = [`<path class="iso-halo" d="${k.haloOf(k.insetPlan(CARRIAGE, 3), CARRIAGE_Z, 0.1, P)}" style="filter:blur(4px)"/>`];
  out.push(S(k.slabOf(CARRIAGE, CARRIAGE_Z, CARRIAGE_TOP - CARRIAGE_Z, P, 5, 0.6), { tone: "mid" }));
  out.push(D([-26, -10, 8, 24].map((x) => at([x, CARRIAGE.y + CARRIAGE.d - 2.6, CARRIAGE_TOP])), { size: 0.4, tone: "lo" }));
  out.push(L(k.lineOnTop([CARRIAGE.x, -16], [CARRIAGE.x + CARRIAGE.w, -16], CARRIAGE_TOP, P), { tone: "faint" }));
  out.push(L(k.lineOnTop([CARRIAGE.x, 16], [CARRIAGE.x + CARRIAGE.w, 16], CARRIAGE_TOP, P), { tone: "faint" }));
  INTENTS.forEach((intent, index) => {
    const plan = { x: -28 + STEP * index, y: -14, w: SLUG_W, d: 28, r: 1 };
    out.push(S(k.slabOf(plan, CARRIAGE_TOP, intent.h, P, 3, 0.5), { tone: "hi", crease: "lo" }));
    out.push(L(k.planOutline(k.insetPlan(plan, 1.6), CARRIAGE_TOP + intent.h, P, 3), { tone: "faint" }));
  });
  const handle = [CARRIAGE.x + CARRIAGE.w - 8, CARRIAGE.y + CARRIAGE.d + 3];
  out.push(S(k.slabOf({ x: handle[0] - 2, y: CARRIAGE.y + CARRIAGE.d - 1, w: 4, d: 4, r: 1 }, CARRIAGE_Z + 1, 3, P, 2), { tone: "mid", crease: "none" }));
  out.push(S(k.cylinder(handle[0], handle[1] + 1, 3, CARRIAGE_Z, 5, P, 20), { tone: "mid" }));
  out.push(L(k.knurl(handle[0], handle[1] + 1, 3, CARRIAGE_Z, CARRIAGE_Z + 5, 18, P), { tone: "lo" }));
  // stamp pad
  out.push(S(k.slabOf({ x: CARRIAGE.x + 8, y: CARRIAGE.y - 8, w: 22, d: 6, r: 1 }, CARRIAGE_TOP, 2.4, P, 3), { tone: "lo" }));
  return out.join("");
}

function plunger() {
  const out = [];
  out.push(S(k.cylinder(DIAL[0], DIAL[1], TIP_R, 0, 2.4, P, 20), { tone: "hi", lit: true }));
  out.push(S(k.cylinder(DIAL[0], DIAL[1], 1.4, 2.4, 48, P, 16), { tone: "hi", crease: "none", lit: true }));
  return out.join("");
}

function dial() {
  const out = [];
  const [x, y] = DIAL;
  out.push(S(k.cylinder(x, y, DIAL_R, DIAL_Z, DIAL_H, P, 64, 0.8), { tone: "hi", crease: "lo" }));
  out.push(L(k.knurl(x, y, DIAL_R, DIAL_TOP - 3.4, DIAL_TOP, 84, P, 0.3), { tone: "lo" }));
  out.push(L(k.sideArc(x, y, DIAL_R, DIAL_TOP - 3.4, P, 40), { tone: "faint" }));
  out.push(L(k.ring(x, y, DIAL_R - 2.2, DIAL_TOP, P, 64), { tone: "lo" }));
  const ticks = k.radialTicks(x, y, DIAL_R - 3, 48, 6, DIAL_TOP, [1.3, 2.8], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(S(k.slabOf({ x: x + DIAL_R - 1, y: -2.4, w: 5, d: 4.8, r: 1.2 }, DIAL_Z + 2, 5, P, 3), { tone: "mid" }));
  out.push(L(k.ring(x, y, 1.6, DIAL_TOP, P, 16), { tone: "mid" }));
  out.push(k.faceTextSvg(k.topMatrix([x, y + 9], DIAL_TOP, P, "x"), "intent", { size: 2.2, tone: "lo", anchor: "middle" }));
  return out.join("");
}

const needleAt = (turn) => {
  const angle = turn * Math.PI * 2;
  const [x, y] = DIAL;
  return k.lineOnTop(
    [x - Math.sin(angle) * 3.4, y + Math.cos(angle) * 3.4],
    [x + Math.sin(angle) * (DIAL_R - 4), y - Math.cos(angle) * (DIAL_R - 4)],
    DIAL_TOP + 0.2,
    P,
  );
};

const startX = STOPS[2];
const startH = INTENTS[2].h;
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "A dispatch desk instrument: a microphone mast feeds a sliding ticket magazine under an intent dial. Six raised slugs stand for rider intents; the dial needle reads the slug under the plunger while a Timbre horn waits for confirmation.",
  body: [
    plate(),
    rails(),
    mic(),
    dialStand(),
    `<g data-part="carriage" transform="${k.translateAlong(P, [startX, 0, 0])}">${carriage()}</g>`,
    `<g data-part="plunger" transform="${k.translateAlong(P, [0, 0, CARRIAGE_TOP + startH])}">${plunger()}</g>`,
    dial(),
    horn(),
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needleAt(startH / PER_TURN)}" style="stroke-width:1.1"/>`,
  ],
});

const live = `
const P = ${JSON.stringify(P)};
const INTENTS = ${JSON.stringify(INTENTS)};
const DIAL = ${JSON.stringify(DIAL)};
const DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP}, PER_TURN = ${PER_TURN}, STEP = ${STEP}, SLUG_W = ${SLUG_W}, TIP_R = ${TIP_R}, BASE = ${CARRIAGE_TOP};
const REACH = ${JSON.stringify(REACH)};
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const carriage = svg.querySelector('[data-part="carriage"]');
const plunger = svg.querySelector('[data-part="plunger"]');
const needle = svg.querySelector('[data-part="needle"]');
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const stops = ${JSON.stringify(STOPS)};
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const heightUnder = (cx) => {
  let top = BASE;
  INTENTS.forEach((intent, index) => {
    const from = cx - 28 + STEP * index, to = from + SLUG_W;
    if (to > DIAL[0] - TIP_R && from < DIAL[0] + TIP_R) top = Math.max(top, BASE + intent.h);
  });
  return top;
};
const intentUnder = (cx) => INTENTS.findIndex((_, index) => { const from = cx - 28 + STEP * index; return DIAL[0] >= from && DIAL[0] <= from + SLUG_W; });
const needleAt = ${needleAt.toString().replace("k.lineOnTop", "lineOnTop")};
let x = ${startX}, target = x, tip = { at: BASE + ${startH}, rate: 0 };
let frame = 0, last = 0, clock = 0, touring = true, visible = false, idleTimer = 0;
const tourAt = (t) => stops[Math.floor(t / 2.0) % stops.length];
function draw() {
  carriage.setAttribute("transform", translateAlong(P, [x, 0, 0]));
  plunger.setAttribute("transform", translateAlong(P, [0, 0, tip.at]));
  needle.setAttribute("d", needleAt((tip.at - BASE) / PER_TURN));
  const index = intentUnder(x);
  const conf = (0.35 + (tip.at - BASE) / 40).toFixed(2);
  const text = (index < 0 ? "scanning" : INTENTS[index].id) + " · confidence " + conf;
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuenow", String(Math.round(tip.at - BASE)));
  stage.setAttribute("aria-valuetext", text);
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  const calm = still.matches;
  if (touring) { clock += dt; target = tourAt(clock); }
  x = calm ? target : x + (target - x) * (1 - Math.exp(-dt / 0.28));
  if (Math.abs(target - x) < 0.01) x = target;
  const want = heightUnder(x);
  const stiff = 420, drag = calm ? 2 * Math.sqrt(420) : 26;
  for (let i = 0; i < 4; i++) { tip.rate += ((want - tip.at) * stiff - tip.rate * drag) * dt / 4; tip.at += tip.rate * dt / 4; }
  if (Math.abs(want - tip.at) < 0.005 && Math.abs(tip.rate) < 0.005) { tip.at = want; tip.rate = 0; }
  draw();
  const settled = !touring && x === target && tip.rate === 0 && tip.at === want;
  frame = visible && !settled ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } };
const steer = (next) => { touring = false; target = clamp(next, REACH[0], REACH[1]); clearTimeout(idleTimer); idleTimer = setTimeout(() => { touring = !still.matches; clock = 0; run(); }, 3600); run(); };
new IntersectionObserver((entries) => { visible = entries[entries.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
if (still.matches) touring = false;
stage.addEventListener("pointermove", (event) => {
  const box = svg.getBoundingClientRect();
  const share = clamp(((event.clientX - box.left) / box.width - 0.22) / 0.56, 0, 1);
  steer(REACH[0] + share * (REACH[1] - REACH[0]));
});
stage.addEventListener("pointerleave", () => steer(target));
stage.addEventListener("keydown", (event) => {
  const here = stops.reduce((best, stop, index) => (Math.abs(stop - target) < Math.abs(stops[best] - target) ? index : best), 0);
  let to = null;
  if (event.key === "ArrowRight" || event.key === "ArrowUp") to = Math.max(0, here - 1);
  if (event.key === "ArrowLeft" || event.key === "ArrowDown") to = Math.min(stops.length - 1, here + 1);
  if (event.key === "Home") to = 0;
  if (event.key === "End") to = stops.length - 1;
  if (to === null) return;
  event.preventDefault();
  steer(stops[to]);
});
draw();
`;

const body = k.plateHtml({
  fig: "Fig 1",
  title: "Dispatch desk",
  hint: "Hover or arrow keys to slide intents",
  readout: `missing · confidence 0.80`,
  keys: [
    { mark: "lit", label: "Plunger and needle: extractor confidence on the selected intent" },
    { mark: "raised", label: "Six ticket slugs: unreachable, address, missing, delay, sos, other" },
  ],
  caption:
    "A bench instrument for Rasta Voice. The microphone stands for rider speech, the sliding magazine holds intent tickets, the dial reads which slug is under the stamp, and the horn is Timbre waiting to speak a confirmation.",
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="Dispatch desk: arrow keys move the intent magazine" aria-valuemin="0" aria-valuemax="20" aria-valuenow="18">${svg}</div>`,
});

const outName = theme === "light" ? "dispatch-desk-light.html" : "dispatch-desk.html";
writeFileSync(join(HERE, outName), k.pageHtml({ title: "Dispatch desk", theme, body, script: kitScript() + live }));
console.log("wrote", outName);
