# Upload parser fixtures

Test-only, 0.1-second synthetic silence, generated locally with FFmpeg from
`anullsrc=r=16000:cl=mono`. No recording, person, transcript or provider output.
Formats: MP3 (libmp3lame), Ogg Opus (libopus), FLAC and M4A (aac).
These files are never loaded by the application. Tests validate their actual
container metadata and do not call a speech API.
