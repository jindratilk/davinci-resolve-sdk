# `audio voice-generate`

Syntax: `cutagent audio voice-generate --voice-id VALUE --text VALUE --output VALUE [--stability VALUE] [--similarity-boost VALUE] [--style VALUE] [--speaker-boost] [--speed VALUE] [--seed VALUE] [--pronunciation-dictionary VALUE] [--previous-text VALUE] [--next-text VALUE] [--previous-request-id VALUE] [--next-request-id VALUE] [--text-normalize VALUE] [--language-text-normalize] [--force]`

## Search terms

- generate ElevenLabs voiceover
- text to speech mp3
- create AI narration
- download generated voice
- synthesize spoken audio
- narrator audio file
- make voiceover for timeline
- add AI voice to DaVinci Resolve

## What it does

Generate and download an ElevenLabs voiceover through CutAgent usage.

## Do not use when

Do not request an ElevenLabs key or CutAgent broker credentials. Do not claim the voiceover is on a DaVinci Resolve timeline merely because the MP3 downloaded; import or append it and verify DaVinci Resolve state separately.

## Preflight and readback

Inspect DaVinci Resolve media-pool or timeline readback after placement and sample render-visible or audible output when the task requires final edit proof.

## Public arguments and options

- `--voice-id` (required) — ElevenLabs voice id from audio voice-list or the public Voice Library
- `--text` (required) — Exact text to synthesize (1-10000 characters)
- `--output/-o` (required) — Destination MP3 path
- `--stability` (optional) — Delivery consistency from 0 to 1
- `--similarity-boost` (optional) — Similarity to the source voice from 0 to 1
- `--style` (optional) — Style exaggeration from 0 to 1
- `--speaker-boost/--no-speaker-boost` (optional) — Override speaker similarity boost
- `--speed` (optional) — Speaking speed from 0.7 to 1.2
- `--seed` (optional) — Best-effort deterministic sampling seed
- `--pronunciation-dictionary` (optional, repeatable) — Pronunciation dictionary as DICTIONARY_ID[:VERSION_ID]; repeat up to 3 times
- `--previous-text` (optional) — Text before this segment for continuity
- `--next-text` (optional) — Text after this segment for continuity
- `--previous-request-id` (optional, repeatable) — Previous ElevenLabs request id; repeat up to 3 times
- `--next-request-id` (optional, repeatable) — Following ElevenLabs request id; repeat up to 3 times
- `--text-normalize` (optional) — Text processing mode: auto, on, or off
- `--language-text-normalize/--no-language-text-normalize` (optional) — Toggle language-specific text processing; currently useful for Japanese and may add latency
- `--force` (optional, default: `false`) — Replace an existing output file

## Boundaries and gotchas

- Text is trimmed and must contain 1 through 10,000 Unicode characters.
- The selected voice id must come from the account's ElevenLabs voice catalog and is bound into the one-time authorization grant.
- Settings and seed are included in the provider idempotency identity, so a retry cannot silently return audio generated with different controls.
- Without `--force`, the destination is reserved atomically before the billable request and an existing path fails closed.
- With `--force`, CutAgent preflights the destination and atomically replaces the existing file only after a successful download.
- Downloads accept only HTTPS Cloudflare R2 signed URLs, reject redirects, enforce a 128 MB limit, and remove an owned incomplete reservation on failure.

## Examples

- `cutagent audio voice-generate --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
