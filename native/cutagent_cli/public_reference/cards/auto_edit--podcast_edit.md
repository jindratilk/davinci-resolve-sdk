# `auto-edit podcast-edit`

Syntax: `cutagent auto-edit podcast-edit [--timeline VALUE] [--angles VALUE] [--transcript VALUE] [--speaker-map VALUE] [--multicam-name VALUE] [--sync VALUE] [--provider VALUE] [--verify] [--checkpoint] [--retries VALUE] [--min-shot-ms VALUE] [--merge-gap-ms VALUE]`

## Search terms

- auto edit podcast by speaker transcript
- switch cameras when each person talks
- build two camera interview from transcript
- active speaker multicam podcast edit
- cut podcast cameras from Scribe transcript
- map transcript speakers to camera angles
- transcript driven interview camera switching
- make podcast edit from speaker labelled JSON

## What it does

Create a podcast multicam edit from a transcript.

## Do not use when

Use `auto-edit podcast-multicam` when switching should be derived from isolated-microphone activity, when a non-mutating `--plan-only` preview is required, or when program audio inside the multicam must be replaced. Use `auto-edit multicam` for explicit segments or a fully structured job with source offsets and settings not exposed by this preset.

## Preflight and readback

Render transcript audio if needed, obtain speaker-labelled JSON, inspect its time units/speaker identifiers, and confirm every speaker maps to a declared angle. Resolve every source clip uniquely in the Media Pool and check duration, fps, audio presence, and desired synchronization method (`in`, `out`, `timecode`, `sound`, or `marker`). Use unique multicam/timeline names and a disposable Disk project or recoverable checkpoint.

## Public arguments and options

- `--timeline` (optional, default: `"Podcast Auto Edit"`) — Target timeline name
- `--angles` (optional) — Angle spec: A=clipA,B=clipB,...
- `--transcript` (optional) — Path to speaker-labelled JSON transcript
- `--speaker-map` (optional) — Optional explicit speaker mapping: speaker_0=A,speaker_1=B
- `--multicam-name` (optional)
- `--sync` (optional, default: `"in"`)
- `--provider` (optional, default: `"ax_native"`)
- `--verify/--no-verify` (optional, default: `true`) — Retained for CLI compatibility; no GUI verification is used
- `--checkpoint` (optional, default: `false`) — Retained for CLI compatibility; ignored
- `--retries` (optional, default: `1`) — Retained for CLI compatibility; ignored
- `--min-shot-ms` (optional, default: `1200`)
- `--merge-gap-ms` (optional, default: `250`) — Merge same-speaker gaps shorter than this

## Boundaries and gotchas

- Duplicate names can be ambiguous; this preset offers no folder/source-path option in `--angles`.
- Explicit `--speaker-map` is safest.
- Unmapped speakers, angle labels absent from `--angles`, malformed timing, or a transcript with no usable rows fail before or during planning.
- Do not claim zero-gap behavior without checking the returned plan.
- `--provider`, `--verify/--no-verify`, `--checkpoint`, and `--retries` are compatibility options only.
- Video-only sources, separate recorder audio, or desired isolated-mic program audio need a different workflow.
- Names must be checked before rerunning to avoid collisions or stale targets.
- Missing inputs are rejected before connecting: the default timeline name satisfies only `timeline`; a bare invocation reports missing `angles` and `transcript` and includes preparation guidance.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent auto-edit podcast-edit --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
