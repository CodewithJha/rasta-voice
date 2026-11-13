import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MISSING_REPLY_AUDIO,
  REPLY_AUDIO_PREFIX,
  renderReplyConfirmation,
  setWavAudio,
} from "../src/reply-view.ts";

test("Hear dispatch shows the exact confirmation text next to the player", async () => {
  const player = { src: "", hidden: true };
  const textEl = { textContent: null as string | null, hidden: true };
  const text = "Gate ke paas ruko, dispatch customer ko call karta hai.";
  renderReplyConfirmation({ text, audio_base64: "ZGF0YQ==" }, player, textEl);
  assert.equal(player.hidden, false);
  assert.ok(player.src.startsWith(REPLY_AUDIO_PREFIX));
  const audio = await fetch(player.src);
  assert.equal(audio.headers.get("Content-Type"), "audio/wav");
  assert.equal(await audio.text(), "data");
  URL.revokeObjectURL(player.src);
  assert.equal(textEl.hidden, false);
  assert.equal(textEl.textContent, text);
});

test("a missing-audio reply does not invent a confirmation", () => {
  const player = { src: "", hidden: true };
  const textEl = { textContent: null as string | null, hidden: true };
  renderReplyConfirmation({ text: "should not appear" }, player, textEl);
  assert.equal(player.hidden, true);
  assert.equal(player.src, "");
  assert.equal(textEl.textContent, MISSING_REPLY_AUDIO);
  assert.notEqual(textEl.textContent, "should not appear");
});


test("replacing an audio source revokes the previous object URL", async () => {
  const player = { src: "", hidden: true };
  setWavAudio(player, "Zmlyc3Q=");
  const previous = player.src;
  setWavAudio(player, "c2Vjb25k");
  assert.notEqual(player.src, previous);
  await assert.rejects(fetch(previous));
  assert.equal(await (await fetch(player.src)).text(), "second");
  URL.revokeObjectURL(player.src);
});
