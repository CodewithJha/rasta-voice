# Rasta Voice

**Hinglish delivery updates, from rider to dispatcher.**

Delivery riders need to explain delays, unreachable customers and delivery
problems in noisy surroundings. Dispatch needs a readable update with an
order number, delay and next action. Rasta Voice connects those two jobs.

A rider submits a short recording, upload or explicitly synthetic sample.
Gnani **Prisma v3.0** transcribes it through REST or streaming. A validated
extractor produces the issue, order identifier, ETA, urgency and suggested
next action. An authenticated dispatch desk receives the stored update and
supports acknowledgement and resolution with an audit trail. Gnani
**Timbre v3.0** produces a spoken confirmation that respects acknowledgement
state. Unclear order numbers prompt clarification instead of a guess.

**Working evidence:** the public noisy sample on 15 November returned a real
Prisma request ID and produced `customer_unreachable`, order `18` and a
10-minute delay. A subsequent browser sample left the order unknown; the
spoken reply requested confirmation. Order recognition is not yet reliable. The rules extractor scored **29/36** on the unchanged
blind intent holdout. CI passes **2,048 Python tests**, coverage/type/contract
checks, frontend and browser checks, security scans, Docker and load tests.

**Scope and limits:** demo audio and the 400-evaluation noise/telephony
benchmark are synthetic. They do not prove accuracy on customer calls or a
carrier network. Consented field validation, live microphone acceptance and
final public video/post evidence remain outstanding. Browser sample and
clarification audio playback were checked; this is not a completed demo video. Public speech has a small
process-local allowance; the desk requires a passcode. The proposed simpler
rider/dispatch UX is in PR 107 and is not yet deployed.

**Team:** Himanshu Kumar built benchmark/audio tooling, verification, CI and
release evidence, contributed extraction corrections and proposed the UX
redesign. Priyanshu Jha built API/extraction integration, streaming, replies,
the original UI, authentication and logging, and implemented rules v2.

**Try:** https://rasta-voice-himanshu748.onrender.com/

**Code:** https://github.com/CodewithJha/rasta-voice

**Evidence and current limits:** [SUBMISSION.md](SUBMISSION.md)
