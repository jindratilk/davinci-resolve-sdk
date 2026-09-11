# `multicam smart-switch`

Syntax: `cutagent multicam smart-switch --multicam-name VALUE --timeline VALUE [--angle VALUE] [--audio-source VALUE] [--audio-angle-map VALUE] [--audio-sync VALUE] [--sync-reference-audio VALUE] [--sync-reference-angle VALUE] [--audio-offsets-json VALUE] [--minimum-edit-duration-ms VALUE] [--edit-change-delay-ms VALUE] [--wide-angle-mode VALUE] [--wide-angle VALUE] [--wide-angle-frequency VALUE] [--wide-intro-outro] [--wide-silence] [--switch VALUE] [--audio-only-fast-analysis] [--analysis-window-ms VALUE] [--activity-floor-db VALUE] [--activity-margin-db VALUE] [--dominance-margin-db VALUE] [--max-silence-hold-ms VALUE] [--video-source-offset VALUE] [--replace-active-timeline] [--plan-only] [--write-plan VALUE]`

## Search terms

- persistent SmartSwitch
- multicam audio activity
- automatic wide angle
- speaker camera switching

## What it does

Create a speaker-aware multicam cut.

## Do not use when

Do not claim parity with viewer-only visual neural analysis. Do not infer speaker-to-angle mappings without evidence. Use `--plan-only` when automatic wide selection or cadence needs review.

## Preflight and readback

Inspect angle roles and audio alignment, then review the JSON plan, selected wide evidence, segments, and pacing. After apply require timeline segment boundaries, selectors, linked audio when requested, save/reopen readback, and complete render with video/audio streams.

## Public arguments and options

- `--multicam-name` (required)
- `--timeline/--timeline-name` (required) — Target timeline name
- `--angle` (optional, repeatable) — Repeatable multicam source spec: A=/path/cam_a.mov
- `--audio-source` (optional, repeatable) — Repeatable isolated speaker audio: speaker_a=/path/mic_a.wav
- `--audio-angle-map` (optional) — Direct isolated-audio mapping: speaker_a=A,speaker_b=B
- `--audio-sync` (optional, default: `"waveform"`)
- `--sync-reference-audio` (optional) — Optional waveform reference file
- `--sync-reference-angle` (optional) — Optional waveform reference angle; defaults to the first angle
- `--audio-offsets-json` (optional)
- `--minimum-edit-duration-ms` (optional, default: `1200`)
- `--edit-change-delay-ms` (optional, default: `500`)
- `--wide-angle-mode` (optional, default: `"automatic"`) — automatic or manual
- `--wide-angle` (optional) — Required when --wide-angle-mode manual
- `--wide-angle-frequency` (optional, default: `"medium"`) — off, low, medium, or high
- `--wide-intro-outro/--no-wide-intro-outro` (optional, default: `true`) — Open and close the cut on the wide angle
- `--wide-silence/--no-wide-silence` (optional, default: `true`) — Use the wide angle when no speaker is active
- `--switch` (optional, default: `"video-only"`) — video-only or video-and-audio
- `--audio-only-fast-analysis/--audio-plus-angle-metadata` (optional, default: `false`) — Use audio alone, or combine it with deterministic angle/shot metadata
- `--analysis-window-ms` (optional, default: `250`)
- `--activity-floor-db` (optional, default: `-50.0`)
- `--activity-margin-db` (optional, default: `6.0`)
- `--dominance-margin-db` (optional, default: `4.0`)
- `--max-silence-hold-ms` (optional, default: `8000`)
- `--video-source-offset` (optional, repeatable) — Per-angle source-frame offset: A=104
- `--replace-active-timeline/--new-timeline` (optional, default: `true`)
- `--plan-only` (optional, default: `false`) — Build the persistent switch plan without applying it
- `--write-plan` (optional) — Optional JSON output path for the plan

## Boundaries and gotchas

- `--audio-sync` accepts waveform, offsets-json, or prealigned.
- `--switch` accepts `video-only` or `video-and-audio`.

## Examples

- `cutagent multicam smart-switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
