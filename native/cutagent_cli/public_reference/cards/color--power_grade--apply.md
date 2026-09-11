# `color power-grade apply`

Syntax: `cutagent color power-grade apply SELECTOR [--clip VALUE]`

## Search terms

- apply a saved PowerGrade
- copy a PowerGrade look to a clip
- use reusable grade from User Gallery
- replace clip grade with PowerGrade still
- apply PowerGrade by index
- apply PowerGrade by label
- load full node graph from PowerGrade
- transplant Gallery grade body
- put saved PowerGrade on current clip
- apply user gallery look with render proof
- restore a reusable Color grade
- copy full Color page correction from PowerGrade

## What it does

Check PowerGrade library apply availability.

## Do not use when

Use `color page primary-set`, wheel/curve/node-specific commands, or selective DRX application when existing target nodes must be preserved—this route replaces the full grade body and offers no append/merge/selective mode.

## Preflight and readback

Ensure the target midpoint is visually representative and that one-frame Deliver rendering, ffmpeg/ffprobe and temporary output are available. Record current playhead and render queue/settings separately because failures after the before-proof do not all reach the normal restoration path.
Check the actual before/after proof images for the requested look, clipping and spatial compatibility; any pixel change is too weak to prove full fidelity. Confirm original playhead, render settings and jobs were restored.

## Public arguments and options

- `SELECTOR` (required) — Power grade selector (index or label)
- `--clip` (optional) — Target clip

## Boundaries and gotchas

- A digit-only selector is always treated as a 1-based index before label matching, so a PowerGrade literally labelled `1` cannot be selected by label if that index points elsewhere.
- The source grade must parse to at least one parameter.
- A graph/body containing only unsupported structure with zero parsed params is rejected even if DaVinci Resolve might otherwise render it.
- The source's version ID/name is not copied; only the body is transplanted into the target's existing/new version object.
- Then Deliver proof requires only any changed pixel.
- Selective modes 1/2 belong to old/unsupported surfaces and must not be inferred.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color power-grade apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
