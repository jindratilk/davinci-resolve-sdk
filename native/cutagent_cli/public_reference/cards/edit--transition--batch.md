# `edit transition batch`

Syntax: `cutagent edit transition batch [TRANSITION_TYPE] [--batch VALUE] [--input VALUE] [--batch-json VALUE] [--select-name-regex VALUE] [--duration-formula VALUE] [--duration-frames VALUE] [--placement VALUE] [--scope VALUE] [--track-type VALUE] [--track VALUE] [--allow-partial]`

## Search terms

- add transitions to many clips
- batch cross dissolve
- put the same transition on matching clips
- add transitions by filename regex
- transition every selected timeline item
- add clip-start and clip-end transitions in bulk
- idempotent transition insertion
- batch audio crossfades
- quarter-length transition formula
- apply transitions from JSON
- skip transitions that already exist
- partially apply a transition batch

## What it does

Add transitions after checking targets.

## Do not use when

Use `edit transition add` when there is exactly one intentional transition and duplicate insertion is desired or must not be silently skipped.
Do not use regex selection when matching an unintended clip would be costly; provide exact JSON entries containing clip name, track and exact start/end frames instead. Do not use `--allow-partial` when all requested transitions must be atomic as a user-level operation: it explicitly permits a valid subset to mutate while other entries fail.

## Preflight and readback

For regex mode, first run the identical command with `--dry-run` and review every resolved target and position; anchor the regex and constrain `--track-type`/`--track` where possible. For JSON mode, prefer exact clip, track type/index, start and end values and decide whether failure of one entry should abort all entries. Inspect adjacent items, available media handles, clip links, track locks and pre-existing transitions because preflight does not.
After mutation, confirm that the intended project and timeline reopened, not `Untitled Project`. Inspect each transition on its exact track and edge, then play or render every changed seam; separately verify linked audio companions and any Smooth Cut split.

## Public arguments and options

- `TRANSITION_TYPE` (optional) — Default transition type, e.g. cross-dissolve
- `--batch` (optional) — JSON batch file
- `--input` (optional) — JSON batch file alias
- `--batch-json` (optional)
- `--select-name-regex` (optional) — Build a batch from matching timeline item names
- `--duration-formula` (optional) — Formula: quarter-clamped
- `--duration-frames` (optional) — Fixed transition duration in frames for selector mode (default: 24)
- `--placement` (optional, default: `"both"`) — Placement: start|end|both
- `--scope` (optional, default: `"video"`) — Transition scope: auto|linked|video|audio
- `--track-type` (optional, default: `"video"`) — Selector track type: video or audio
- `--track/--track-index` (optional) — Optional selector track index
- `--allow-partial` (optional, default: `false`) — Apply valid entries even when some entries fail preflight

## Boundaries and gotchas

- Exactly one input source is required in JSON mode.
- Supplying neither, or combining `--batch`, `--input` and `--batch-json`, fails.
- `--track-type` and `--track` filter discovery; they do not change the destination track.
- Duplicate names are ambiguous unless further constrained.
- Only `cross-dissolve`, `smooth-cut`, `cross-fade+3db`, `cross-fade-0db`, `cross-fade-3db`, `rotate-90` and `zoom-in` are accepted.
- Scope and placement may also be overridden per JSON entry.
- `quarter-clamped` is the only formula.
- It does not use source-handle length.
- Cross Dissolve and Smooth Cut auto scope resolve to linked, audio crossfades to audio and Fusion transitions to video.
- The command default is explicitly `video`, however, so omitting `--scope auto` does not request linked audio.
- Start/end preflight does not require an adjacent clip or media handles.
- Idempotent skip is not a cheap read-only check.
- `--allow-partial` only changes preflight handling.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent edit transition batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
