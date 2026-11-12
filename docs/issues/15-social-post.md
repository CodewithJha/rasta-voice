# 15 — LinkedIn and X post

- **Labels:** `area:app`, `day:3`, `outreach`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio (moved from Member B / Priyanshu on 12 Nov to balance load)
- **Target day:** Day 3, and the post is **live by 14 Nov 2026, 18:00 IST**. Draft earlier the same day. Do not wait on the full benchmark if it is late. However, the contest post needs a real public **working-application video**, not merely a phone photo of the slate. Record a truthful simple video first; see the video/submission issue.
- **Depends on:** issue 09, so you have something true to describe. Issue 12 is optional input: quote a number only from the committed live `scores.json`. If it is not in yet, describe the live sample result (README) instead of a number.

## Description

Write `docs/social-post.md` with two posts the team can paste.

**X** (`https://x.com/GnaniAi`): one post, 280 characters or under, including the hashtags and the mention. If the story does not fit, a thread of two posts, each ≤ 280, and the hashtags live on the first.

**LinkedIn** (company page to tag: `https://www.linkedin.com/company/gnani-ai`): up to about 150 words. Tag the company. Same hashtags.

Both posts must include, in the words you actually publish:

- The product name, Rasta Voice, and the rider-in-traffic situation.
- That the speech path uses Gnani Prisma (and Timbre, if issue 08 has merged; if it has not, don't claim the reply is live).
- The award you are aiming at: Noise Canceller.
- Hinglish, in one clause.
- The hashtags `#GnaniAI` and `#GreatIndianAIInternshipChallenge`.
- One sentence that the audio is synthetic and there are no real customer calls.
- The repo URL and, if issue 13 has a URL, the live desk URL.

Both posts must not include:

- A fake WER, a fake latency, or "production-ready".
- A real phone number, a real order, or a real customer's words.
- More than one emoji, and none is required.

At the bottom of the file, a checklist:

- [ ] Posted on X by 14 Nov 2026, 18:00 IST. Link:
- [ ] Posted on LinkedIn by the same deadline. Link:

Fill the links when you post. The draft without links can merge first; a follow-up commit adds the links the same day. The issue is not done until the links are in the file.

Priyanshu (Member B) reads the draft once for the app claims before you post, and supplies the video from #18. If they are not around, you still post, and you do not invent any number or feature.

## Files to touch

- `docs/social-post.md` (new)

## Do not touch

Application code, the README benchmark section, `benchmark/results/`.

## Input / output contract

The file has two headings, `## X` and `## LinkedIn`, the text to paste under each, a character count under the X post, and the checklist. The X count is computed by you (a `python -c` len of the post). Spaces count.

## Acceptance criteria

- [ ] X post length ≤ 280, or each thread post ≤ 280.
- [ ] Both hashtags appear in both posts, spelled exactly as above.
- [ ] `@GnaniAi` appears in the X post. The LinkedIn post names Gnani AI and uses the company URL.
- [ ] Synthetic-data sentence is present in both.
- [ ] No digit run of 8 or more.
- [ ] Links to the live posts are filled in before 14 Nov 2026, 18:00 IST.

## How to test

```bash
python -c "
import pathlib, re
text = pathlib.Path('docs/social-post.md').read_text()
x = text.split('## LinkedIn')[0].split('## X', 1)[1]
# count the fenced block you tell the script to use; keep the post in one fence
fence = re.findall(r'```(.*?)```', x, re.S)[0]
print(len(fence.strip()))
"
```

Paste into the X compose box as a second check. The site's counter wins if it disagrees.

<!-- rasta-voice-audit-2026-11-12 -->

### Public video requirement

Official requirements: https://www.gnani.ai/internship

- [ ] A public working-application **video is attached/linked to the nominated post**. Photo-only posts do not count as a completed demo entry.
- [ ] Both required hashtags and the Gnani AI tag are on each nominated post; draft post links are not accepted as final links.
- [ ] The post is truthful about simulated noise and any unimplemented features. Avoid unsupported WER, false live-call claims, and misleading engagement tactics.
- [ ] Record the publicly accessible video and nominated post links in the video/submission evidence issue and pass them to #16.

