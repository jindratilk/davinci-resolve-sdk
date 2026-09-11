# `text insert-captions`

Syntax: `cutagent text insert-captions [--spec VALUE] [--spec-json VALUE]`

## Search terms

- designed transcript captions
- segment transcript into Text+
- explicit caption segmentation
- caption reading speed CPS
- one-line caption plan
- timed word captions
- empty track above occupied
- caption setting template
- Text+ caption batch

## What it does

Create designed captions from the transcript.

## Do not use when

It creates designed Text+ clips from an already available transcript.
Do not use a named segmentation preset or omit any segmentation limit. Do not use a stale transcript, estimated timing without reviewing warnings, or a non-empty production track unless overlap and cleanup consequences are explicitly acceptable.
Note that dry-run itself requires a connected timeline and inspects track occupancy.

## Preflight and readback

Save/checkpoint the project and inspect every video track.
Also review frame-adjustment warnings, selected track, track creation plan, and rendered template checks.
Inspect representative and boundary captions visually with frame exports or rendered output.

## Public arguments and options

- `--spec` (optional) — Path to transcript caption insertion JSON spec
- `--spec-json` (optional) — Inline transcript caption insertion JSON spec

## Boundaries and gotchas

- Exactly one of `--spec` and `--spec-json` is required.
- `--spec` expands `~`, converts to an absolute path, and must name an existing file.
- The outer spec must be valid JSON and must be a JSON object.
- A valid dry-run therefore requires an active timeline and embedded bridge.
- The raw spec must not contain `preset`; named caption presets are explicitly rejected.
- Required caption fields are `transcript`, `template`, and `segmentation`.
- The transcript path is stripped, expands `~`, becomes absolute, and must be an existing file.
- Transcript JSON must be readable and must contain an object.
- `unit` must be `words` or `characters`.
- Six length/line settings must be positive integers.
- Four timing settings must be finite and greater than zero.
- It preserves token order and does not mix speakers across a cue.
- Cue duration is extended toward the configured minimum/hard-CPS requirement only up to the next cue start.
- Caption specs do not directly provide `items`; the segmenter creates them and rejects an empty plan.
- The template must exist and each rendered item must produce valid text/template placeholder checks.
- By default, the target track must be empty and above every occupied video track.
- Verification requires exact planned count and placement; sampled accessible Fusion graphs must contain TextPlus and MediaOut.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent text insert-captions --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
