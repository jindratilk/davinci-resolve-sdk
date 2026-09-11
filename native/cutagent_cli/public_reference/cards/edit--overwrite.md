# `edit overwrite`

Syntax: `cutagent edit overwrite CLIP_NAME --at VALUE [--in VALUE] [--out VALUE] [--track VALUE] [--media-id VALUE] [--audio-track VALUE] [--include-linked-audio] [--project-id VALUE] [--timeline-id VALUE] [--revision VALUE]`

## Search terms

- replace an exact timeline range without ripple
- checkpoint-backed overwrite edit
- preserve ordinary clip heads and tails
- replace linked video and audio range

## What it does

Overwrite clips at the timeline position.

## Do not use when

Use a narrower audio/video command when linked companions must remain outside the explicit target tracks.
Do not use overwrite to cut through transitions or to partially reconstruct a clip with markers, flags, clip color, disabled state, retiming/speed ramps, local color grades, non-default transforms/crops/scaling/compositing, clip audio gain/fades/EQ/FX/channel remapping, Fusion compositions or multiple takes. Fully covered items are intentionally removed, so inspect the dry-run impact list before approving the mutation.

## Preflight and readback

Run dry-run first.

## Public arguments and options

- `CLIP_NAME` (required) — Media pool clip name
- `--at/--record-frame` (required) — Timeline record-domain position
- `--in/--source-in` (optional) — Half-open source-domain range start
- `--out/--source-out` (optional) — Half-open source-domain range end (exclusive)
- `--track` (optional, default: `1`) — One-based target video track
- `--media-id` (optional) — Authoritative Media Pool item identity
- `--audio-track` (optional) — One-based linked-audio target track
- `--include-linked-audio/--video-only` (optional, default: `true`) — Overwrite and verify source audio when present
- `--project-id` (optional) — Expected active project identity
- `--timeline-id` (optional) — Expected active timeline identity
- `--revision` (optional) — Expected timeline revision from a prior dry run

## Boundaries and gotchas

- At fractional rates such as 23.976 or 29.97 fps, use explicit frame references such as `120f`; colon/semicolon timecode is rejected because it cannot prove an exact source-frame boundary.
- `--track` and `--audio-track` are one-based explicit targets.
- Source audio is included and linked by default when its metadata proves audio exists; `--video-only` opts out.
- Any target-range transition conflict is rejected because this route cannot reconstruct transition semantics.
- A partially covered ordinary clip must have authoritative media/source identity and reconstructible state.
- Rebuilt edges receive new timeline-item IDs, but exact source/record ranges, state digests and A/V links must verify.
- Dry-run does not create or expose a private checkpoint path.

## Stable public error codes

- `AMBIGUOUS_MEDIA_POOL_ITEM`
- `EDIT_MUTATION_FAILED_BEFORE_CHANGE`
- `EDIT_MUTATION_PARTIALLY_APPLIED`
- `EDIT_MUTATION_RECOVERY_FAILED`
- `EDIT_MUTATION_RESTORED`
- `INVALID_TIME_REFERENCE`
- `TIMELINE_CONFLICT`

## Examples

- `cutagent edit overwrite --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
