# `color source-grade apply-cdl`

Syntax: `cutagent color source-grade apply-cdl [--version-name VALUE] [--clip VALUE] [--node VALUE] [--slope VALUE] [--offset VALUE] [--power VALUE] [--sat VALUE] [--include-singletons] [--proof-instances VALUE]`

## Search terms

- apply shared source grade CDL
- grade all cuts from same source
- use Remote Grade across timeline instances
- set CDL on remote color version
- correct repeated source clips once
- source-level slope offset power saturation
- make one grade affect every reused clip
- create remote version and apply CDL
- proof shared grade on multiple cuts
- color-correct repeated takes globally
- use DaVinci Resolve Remote Grade
- apply one primary correction to all source instances

## What it does

Apply a CDL to one shared remote and source grade and proof multiple same-source timeline instances.

## Do not use when

Use `color source-grade plan` first when it is not yet known whether source scope is appropriate. Use `color source-grade prepare-remote` when only version creation/loading is desired without a CDL. Use ordinary `color cdl` for a local timeline-item correction that should not propagate through a shared Remote Grade. Use `color grade-copy` when each target should receive an independent editable local copy. Do not use Remote Grade for a singleton unless the user explicitly accepts source scope and `--include-singletons`; default behavior recommends timeline-local. Avoid reusing an existing `--version-name` when its previous contents must be preserved, because the active shared version is overwritten in place.

## Preflight and readback

Before applying, run `color source-grade plan --scope current-source` and inspect every returned source identity, track/index/start/duration. Confirm all matching cuts should share the correction, choose a unique or intentionally reusable Remote Version name, list existing local/remote versions, and capture current version/playhead/page. For repeated sources require at least two proof instances, preferably all visually diverse cuts. Save/export the project or grade because remote preparation and mutation are not rolled back on later errors.
Inspect PNGs and their target identities; an arbitrary pixel change is not semantic proof. If any stage errors, immediately re-list versions/current version, inspect the target grade and restore page/playhead manually; do not assume failure was a no-op.

## Public arguments and options

- `--version-name` (optional, default: `"CutAgent Source Grade"`) — Remote source color version to create/load
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node` (optional, default: `1`) — Node index
- `--slope` (optional) — Slope as 'R G B'
- `--offset` (optional) — Offset as 'R G B'
- `--power` (optional) — Power as 'R G B'
- `--sat` (optional) — Saturation
- `--include-singletons` (optional, default: `false`) — Allow a one-off source to use remote scope
- `--proof-instances` (optional, default: `2`) — Number of same-source instances to render-proof; 0 means all

## Boundaries and gotchas

- The source group is built only from video items in the current timeline.
- With multiple instances, `--proof-instances 1` is explicitly rejected.
- Triplet parsing requires exactly three numeric tokens but does not reject non-finite floats such as `nan`/`inf`; saturation is stringified without finiteness/range validation.
- It does not prove intended direction, magnitude, gamut safety or aesthetic quality.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color source-grade apply-cdl --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
