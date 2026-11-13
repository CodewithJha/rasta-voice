import http from "k6/http";
import exec from "k6/execution";
import { sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { configuration } from "./config.mjs";

const config = configuration(__ENV);
const healthMs = new Trend("health_ms", true);
const readyMs = new Trend("ready_ms", true);
const deskMs = new Trend("desk_ms", true);
const speechMs = new Trend("speech_ms", true);
const opsErrors = new Rate("ops_errors");
const deskErrors = new Rate("desk_errors");
const speechErrors = new Rate("speech_errors");
const healthCalls = new Counter("health_calls");
const readyCalls = new Counter("ready_calls");
const deskCalls = new Counter("desk_calls");
const speechCalls = new Counter("speech_calls");
let unlocked = false; // Each k6 VU has its own instance and cookie jar.

const scenarios = {
  ops: { executor: "constant-vus", exec: "ops", vus: 20, duration: "30s", gracefulStop: "5s" },
};
const thresholds = {
  health_ms: [`p(95)<${config.profile === "local" ? 100 : 300}`],
  ready_ms: [`p(95)<${config.profile === "local" ? 300 : 800}`],
  ops_errors: ["rate<=0.01"],
  health_calls: ["count>0"],
  ready_calls: ["count>0"],
};
if (config.desk) {
  scenarios.desk = { executor: "constant-vus", exec: "desk", vus: 10, duration: "30s", gracefulStop: "5s" };
  thresholds.desk_ms = [`p(95)<${config.profile === "local" ? 300 : 800}`];
  thresholds.desk_errors = ["rate<=0.01"];
  thresholds.desk_calls = ["count>0"];
}
if (config.speech) {
  // Four iterations shared across both VUs, never four per VU.
  scenarios.speech = { executor: "shared-iterations", exec: "speech", vus: 2, iterations: 4, maxDuration: "70s", gracefulStop: "0s" };
  thresholds.speech_ms = ["p(95)<8000"];
  thresholds.speech_errors = ["rate==0"];
  thresholds.speech_calls = ["count>0", "count<=4"];
}

export const options = {
  scenarios, thresholds, noCookiesReset: true, maxRedirects: 0,
  summaryTrendStats: ["med", "p(95)"],
  // Omit URL tags from optional metric outputs; names are fixed below.
  systemTags: ["scenario", "name", "status", "method", "expected_response"],
};

function params(name, timeout = "5s") {
  return { timeout, redirects: 0, tags: { name } };
}

function okJson(response, predicate) {
  if (response.status !== 200) return false;
  try { return predicate(response.json()); } catch { return false; }
}

export function ops() {
  const health = http.get(`${config.base}/api/health`, params("health"));
  healthCalls.add(1);
  healthMs.add(health.timings.duration);
  opsErrors.add(!okJson(health, (body) => body.ok === true && typeof body.gnani_key_set === "boolean"));
  const ready = http.get(`${config.base}/api/ready`, params("ready"));
  readyCalls.add(1);
  readyMs.add(ready.timings.duration);
  opsErrors.add(!okJson(ready, (body) => body.ok === true && body.db_writable === true));
  sleep(1);
}

export function desk() {
  if (!unlocked) {
    const p = params("desk_unlock");
    p.headers = { "Content-Type": "application/json" };
    const response = http.post(`${config.base}/api/dispatch/unlock`, JSON.stringify({ passcode: __ENV.DISPATCH_PASSCODE }), p);
    const good = okJson(response, (body) => body.ok === true);
    deskErrors.add(!good);
    if (!good) exec.test.abort("Desk unlock failed; stopping without logging credentials or response bodies.");
    unlocked = true;
  }
  const response = http.get(`${config.base}/api/events`, params("desk_events"));
  deskCalls.add(1);
  deskMs.add(response.timings.duration);
  deskErrors.add(!okJson(response, (body) => Array.isArray(body.events)));
  sleep(1);
}

export function speech() {
  // Defence against accidentally overriding the scenario's iteration count.
  if (exec.scenario.iterationInTest >= 4) return;
  speechCalls.add(1);
  const response = http.post(`${config.base}/api/ingest/sample`, null, params("speech_sample", "30s"));
  speechMs.add(response.timings.duration);
  const id = Object.entries(response.headers).find(([name]) => name.toLowerCase() === "x-request-id");
  const good = response.status === 200 && Boolean(id && typeof id[1] === "string" && id[1].trim());
  speechErrors.add(!good);
  // abort() stops the whole run. An already-outbound second VU cannot be recalled.
  if (response.status === 429) exec.test.abort("Speech returned 429; stopping all further iterations.");
  if (!good) exec.test.abort("Speech failed or omitted X-Request-ID; stopping without retrying.");
}

export function handleSummary(data) {
  const value = (name, key) => data.metrics[name]?.values?.[key];
  const count = (name) => value(name, "count") || 0;
  const duration = (name) => ({ p50_ms: value(name, "med") ?? null, p95_ms: value(name, "p(95)") ?? null });
  const report = {
    profile: config.profile,
    ops_vus: 20, desk_vus: config.desk ? 10 : 0, speech_vus: config.speech ? 2 : 0,
    configured_ops_seconds: 30,
    elapsed_seconds: data.state?.testRunDurationMs ? data.state.testRunDurationMs / 1000 : null,
    health: { ...duration("health_ms"), calls: count("health_calls") },
    ready: { ...duration("ready_ms"), calls: count("ready_calls") },
    desk: { ...duration("desk_ms"), calls: count("desk_calls") },
    speech: { ...duration("speech_ms"), calls: count("speech_calls") },
    ops_error_rate: value("ops_errors", "rate") ?? null,
    desk_error_rate: value("desk_errors", "rate") ?? null,
    speech_error_rate: value("speech_errors", "rate") ?? null,
    thresholds_passed: Object.values(data.metrics).every((metric) => Object.values(metric.thresholds || {}).every((test) => test.ok)),
  };
  const output = { stdout: `\nRasta load measurements (milliseconds; null means not measured)\n${JSON.stringify(report, null, 2)}\n` };
  if (__ENV.SUMMARY_PATH) output[__ENV.SUMMARY_PATH] = JSON.stringify(report, null, 2) + "\n";
  return output;
}
