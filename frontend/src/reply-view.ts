/** Render a Timbre confirmation without depending on the chit CSS. */

export interface ReplyPayload {
  text?: string;
  audio_base64?: string;
}

export interface AudioTarget {
  src: string;
  hidden: boolean;
}

export interface TextTarget {
  textContent: string | null;
  hidden?: boolean;
}

export const REPLY_AUDIO_PREFIX = "blob:";

/** Same-origin object URLs keep audio compatible with the strict media policy. */
export function setWavAudio(player: AudioTarget, audioBase64: string): void {
  const bytes = Uint8Array.from(atob(audioBase64), (character) => character.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/wav" }));
  if (player.src.startsWith(REPLY_AUDIO_PREFIX)) {
    URL.revokeObjectURL(player.src);
  }
  player.src = url;
  player.hidden = false;
}
export const MISSING_REPLY_AUDIO = "The reply had no audio.";

export function renderReplyConfirmation(
  payload: ReplyPayload,
  player: AudioTarget,
  textEl: TextTarget,
): void {
  if (!payload.audio_base64) {
    textEl.textContent = MISSING_REPLY_AUDIO;
    textEl.hidden = false;
    return;
  }
  setWavAudio(player, payload.audio_base64);
  if (payload.text) {
    textEl.textContent = payload.text;
    textEl.hidden = false;
  }
}
