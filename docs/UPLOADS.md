# Audio upload limits

The public ingest and simulator routes accept a single `audio_file` multipart
field. The audio file is at most 2,000,000 bytes and 30 seconds. The entire HTTP
body also has a 64 KiB allowance for multipart headers and boundaries. Both the
advertised length and actual received bytes are checked; chunked requests do
not bypass the ceiling.

Accepted uploads stay in memory, including files above the framework's default
1 MiB spool threshold. Malformed or rejected requests close their temporary
in-memory handles. The server normalizes the filename to an ASCII basename of
at most 64 characters and gives it the extension detected from the container.
A `.wav` filename does not make text or a corrupt file valid audio.

`POST /api/ingest` recognizes PCM WAV, MP3, Ogg Vorbis/Opus/FLAC, FLAC and M4A
containers and checks their duration metadata before calling Prisma. WAV
length uses the PCM frames actually present; MP3 inspection does not decode
ID3 tag payloads. Container validation does not replace the provider's audio
decoder: a later provider failure remains an error, never a fake transcript.
The existing `/api/simulate` noise conversion still requires its supported
8/16 kHz mono PCM WAV input; recognizing another format does not transcode it.

Oversize or overlong input returns 413 `payload_too_large`. Unrecognized or
invalid containers return 415 `unsupported_media_type`; empty audio returns
400 `validation_error`. Upload rejections have a safe `error` object with a
message and request ID. No original filename, audio contents or parser error
is reflected in that message. Other API error contracts remain issue 26.

The regression suite includes real short synthetic-silence containers, a valid
1.23 MB seven-second WAV that must never roll to disk, chunked and understated
lengths, exact/over-30-second PCM, corrupt magic, safe names and handle cleanup.
Fixtures are test-only and never stand in for provider output in the app.
