import test from "node:test";
import assert from "node:assert/strict";
import { configuration } from "../config.mjs";

test("speech defaults off and loopback uses local budgets", () => {
  assert.deepEqual(configuration({}), { base: "http://127.0.0.1:8000", local: true, profile: "local", speech: false, desk: false });
});
test("speech permits the three exact loopback hosts", () => {
  for (const host of ["localhost", "127.0.0.1", "[::1]"]) {
    assert.equal(configuration({ BASE_URL: `http://${host}:8000/`, SPEECH: "1" }).speech, true);
  }
});
test("public contest and misleading staging hosts cannot enable speech", () => {
  for (const host of ["rasta.hf.space", "stagingevil.example", "contest.example", "localhost.evil.example"]) {
    const base = `https://${host}`;
    assert.throws(() => configuration({ BASE_URL: base, STAGING_BASE_URL: base, SPEECH: "1" }), /Speech needs/);
  }
});
test("a named HTTPS staging host also needs an exact explicit opt-in", () => {
  const base = "https://rasta-staging.example";
  assert.equal(configuration({ BASE_URL: base, STAGING_BASE_URL: base, SPEECH: "1" }).speech, true);
  assert.throws(() => configuration({ BASE_URL: base, SPEECH: "1" }), /Speech needs/);
  assert.throws(() => configuration({ BASE_URL: base, STAGING_BASE_URL: base + "/", SPEECH: "1" }), /Speech needs/);
  assert.throws(() => configuration({ BASE_URL: "http://staging.example", STAGING_BASE_URL: "http://staging.example", SPEECH: "1" }), /Speech needs/);
});
test("CI rejects speech even on loopback or approved staging", () => {
  for (const ci of ["1", "true", "TRUE", "github"]) {
    assert.throws(() => configuration({ SPEECH: "1", CI: ci }), /disabled in CI/);
  }
});
test("origins cannot hide credentials or a query key", () => {
  for (const base of ["https://user:secret@staging.example", "https://staging.example?key=secret", "https://staging.example/#secret", "ftp://staging.example", "https://staging.example/path", "http://localhost:0", "http://localhost:65536"]) {
    assert.throws(() => configuration({ BASE_URL: base }), /HTTP\(S\) origin/);
  }
});
test("invalid opt-in and budget profiles fail before requests", () => {
  assert.throws(() => configuration({ SPEECH: "yes" }), /SPEECH/);
  assert.throws(() => configuration({ PROFILE: "relaxed" }), /PROFILE/);
});
