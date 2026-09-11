# `color page shot-match-apply`

Syntax: `cutagent color page shot-match-apply [CLIP_NAME] --reference-at VALUE [--target-at VALUE] [--reference-output VALUE] [--target-output VALUE] [--anchor-x VALUE] [--anchor-y VALUE] [--radius VALUE] [--strength VALUE]`

## Search terms

- apply shot match gains
- make target shot match reference
- balance two camera angles automatically
- copy reference color balance to target
- correct RGB mismatch between clips
- apply conservative camera match
- match exposure and white balance
- anchor-based shot match correction
- normalize target shot to reference frame
- fix inter-camera color difference
- apply analyzed RGB gain ratios

## What it does

Apply a conservative RGB gain shot-match correction from reference and target frame analysis.

## Do not use when

Use `color page shot-match-analyze` first when the user has not approved a grade mutation, the corresponding regions are uncertain, or raw/clamped recommendations need review. Use `color page primary-set` when explicit artist-chosen primary values should be written, and use `color page white-balance-picker` when one known neutral patch—not a separate reference shot—should determine balance.

## Preflight and readback

Create a recoverable checkpoint and ensure embedded close/reopen is ready for the exact local Disk project.

## Public arguments and options

- `CLIP_NAME` (optional) — Target clip name; current target frame clip when omitted
- `--reference-at` (required) — Timeline position for the reference shot/frame
- `--target-at` (optional) — Timeline position for the target shot/frame; current playhead when omitted
- `--reference-output` (optional, default: `"color_shot_match_reference.png"`) — Exported reference frame path
- `--target-output` (optional, default: `"color_shot_match_target.png"`) — Exported target frame path
- `--anchor-x` (optional) — Optional normalized shared anchor X coordinate, 0..1
- `--anchor-y` (optional) — Optional normalized shared anchor Y coordinate, 0..1
- `--radius` (optional, default: `12`) — Anchor sample radius in pixels, 0..200
- `--strength` (optional, default: `0.5`) — Applied RGB gain strength, 0..1

## Boundaries and gotchas

- There is no `--node` option.
- Severe mismatches therefore produce a limited correction; `clamped=true` must be reviewed rather than treated as a match.
- Only gain changes.
- Output paths are not required to be distinct.
- Reusing one leaves only the target image on disk, even though reference pixels remained in memory for analysis.
- Local Disk mutation must use the embedded lifecycle.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page shot-match-apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
