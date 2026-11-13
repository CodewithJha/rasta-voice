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

export const REPLY_AUDIO_PREFIX = "data:audio/wav;base64,";
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
  player.src = `${REPLY_AUDIO_PREFIX}${payload.audio_base64}`;
  player.hidden = false;
  if (payload.text) {
    textEl.textContent = payload.text;
    textEl.hidden = false;
  }
}
