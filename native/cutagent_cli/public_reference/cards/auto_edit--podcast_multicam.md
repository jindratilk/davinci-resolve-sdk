# `auto-edit podcast-multicam`

Syntax: `cutagent auto-edit podcast-multicam --timeline VALUE --angles VALUE [--switch-by VALUE] [--transcript VALUE] [--speaker-map VALUE] [--audio-source VALUE] [--audio-angle-map VALUE] [--audio-target VALUE] [--audio-sync VALUE] [--sync-reference-audio VALUE] [--sync-reference-angle VALUE] [--audio-offsets-json VALUE] [--overlap-policy VALUE] [--overlap-angle VALUE] [--analysis-window-ms VALUE] [--activity-floor-db VALUE] [--activity-margin-db VALUE] [--dominance-margin-db VALUE] [--min-switch-ms VALUE] [--switch-delay-ms VALUE] [--max-silence-hold-ms VALUE] [--program-audio-source VALUE] [--replace-program-audio] [--program-audio-unmapped VALUE] [--plan-only] [--write-plan VALUE] [--multicam-name VALUE] [--sync VALUE] [--provider VALUE] [--verify] [--checkpoint] [--retries VALUE] [--min-shot-ms VALUE] [--merge-gap-ms VALUE]`

## Search terms

- podcast multicam from active speaker
- switch cameras from speaker transcript
- switch podcast cameras from isolated microphones
- audio activity camera switching
- plan podcast camera cuts without applying
- map lav mics to camera angles
- use wide shot during overlapping speech
- replace multicam program audio with isolated mics

## What it does

Create a podcast multicam edit.

## Do not use when

Use `auto-edit multicam` when segments are already decided or the complete structured job must be supplied directly. Use `audio duck` or Fairlight commands when the goal is mixing rather than changing camera angles. Do not use audio-activity mode on the final stereo mix when isolated speaker sources are required to distinguish who is active.

## Preflight and readback

For transcript mode, validate transcript rows and speaker mapping. Independently verify that each `--angles` clip exists uniquely in the Media Pool, because transcript plan-only does not.

## Public arguments and options

- `--timeline` (required) — Target timeline name
- `--angles` (required) — Angle spec: A=clipA,B=clipB,...
- `--switch-by` (optional, default: `"transcript"`) — Switch planner: transcript or audio-activity
- `--transcript` (optional) — Path to ElevenLabs Scribe v2 JSON transcript
- `--speaker-map` (optional) — Optional explicit speaker mapping: speaker_0=A,speaker_1=B
- `--audio-source` (optional, repeatable) — Repeatable audio activity source spec: id=/path/audio.wav
- `--audio-angle-map` (optional) — Audio activity mapping: source_id=ANGLE,source_id=ANGLE
- `--audio-target` (optional, repeatable) — Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B
- `--audio-sync` (optional) — Audio sync mode for audio-activity: prealigned, waveform, offsets-json
- `--sync-reference-audio` (optional) — Reference camera/audio file for waveform audio sync
- `--sync-reference-angle` (optional) — Reference angle for waveform audio sync when the angle has a source path
- `--audio-offsets-json` (optional) — Path to JSON offsets object for audio-activity sync
- `--overlap-policy` (optional) — Overlap handling: angle/wide, dominant, hold, mark
- `--overlap-angle/--wide-angle` (optional) — Multicam angle to use for overlap/wide moments
- `--analysis-window-ms` (optional) — Audio activity analysis window in milliseconds
- `--activity-floor-db` (optional) — Absolute dBFS floor required for activity
- `--activity-margin-db` (optional) — dB above per-source noise floor required for activity
- `--dominance-margin-db` (optional) — Leader margin in dB required before avoiding overlap handling
- `--min-switch-ms` (optional) — Minimum planned video switch duration in milliseconds
- `--switch-delay-ms` (optional) — New audio target must persist this long before switching
- `--max-silence-hold-ms` (optional) — Hold previous angle through silence up to this duration
- `--program-audio-source` (optional, repeatable)
- `--replace-program-audio` (optional, default: `false`)
- `--program-audio-unmapped` (optional, default: `"remove"`)
- `--plan-only` (optional, default: `false`) — Build and return the switch plan without creating/applying the edit
- `--write-plan` (optional) — Optional JSON path to write the generated switch plan
- `--multicam-name` (optional)
- `--sync` (optional, default: `"in"`)
- `--provider` (optional, default: `"ax_native"`)
- `--verify/--no-verify` (optional, default: `true`) — Retained for CLI compatibility; no GUI verification is used
- `--checkpoint` (optional, default: `false`) — Retained for CLI compatibility; ignored
- `--retries` (optional, default: `1`) — Retained for CLI compatibility; ignored
- `--min-shot-ms` (optional, default: `1200`)
- `--merge-gap-ms` (optional, default: `250`) — Merge same-speaker gaps shorter than this

## Boundaries and gotchas

- Transcript plan-only uses a synthetic context with fps 24 and start frame 0.
- It does not connect to DaVinci Resolve, resolve Media Pool source names, infer actual source durations, or use the current timeline start.
- Transcript mode requires `--transcript`; audio-activity mode requires `--audio-sync` and at least usable audio sources/mappings.
- `--provider`, `--verify`, `--checkpoint`, and `--retries` are compatibility fields only and do not change execution, add GUI checking/checkpoints, or retry.
- Use `keep` only after deciding that mixed source audio is desirable.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent auto-edit podcast-multicam --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
