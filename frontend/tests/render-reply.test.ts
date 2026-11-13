import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MISSING_REPLY_AUDIO,
  REPLY_AUDIO_PREFIX,
  renderReplyConfirmation,
} from "../src/reply-view.ts";

test("Hear dispatch shows the exact confirmation text next to the player", () => {
  const player = { src: "", hidden: true };
  const textEl = { textContent: null as string | null, hidden: true };
  const text = "Gate ke paas ruko, dispatch customer ko call karta hai.";
  renderReplyConfirmation({ text, audio_base64: "ZGF0YQ==" }, player, textEl);
  assert.equal(player.hidden, false);
  assert.equal(player.src, `${REPLY_AUDIO_PREFIX}ZGF0YQ==`);
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
