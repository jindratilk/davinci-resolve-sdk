# `color page rgb-mixer-set`

Syntax: `cutagent color page rgb-mixer-set [CLIP_NAME] [--node-index VALUE] [--monochrome] [--preserve-luminance] [--red VALUE] [--green VALUE] [--blue VALUE]`

## Search terms

- make clip black and white with RGB Mixer
- enable monochrome RGB Mixer
- preserve luminance monochrome grade
- turn off RGB Mixer monochrome
- convert color clip to grayscale on Color page
- Color page black-and-white grade
- RGB Mixer channel coefficients
- mix red green blue channels
- desaturate with RGB Mixer instead of saturation
- set RGB Mixer on a grade node

## What it does

Runs the public `color page rgb-mixer-set` CutAgent command.

## Do not use when

Use `color page primary-set --sat 0` when the request is simply to remove saturation with the primary controls; that remains a different grading operation from RGB Mixer Monochrome and can produce different luminance. Use node-management commands first if the requested node does not already exist.

## Preflight and readback

After the project reopens, require the command's exact mode readback (`4` when enabled, absent/non-`4` when disabled), confirm the intended project/timeline/clip and grade version returned, and export or inspect a frame to prove the rendered image is monochrome. Compare against a pre-edit frame if luminance preservation matters; the built-in verification does not compare pixels.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index
- `--monochrome/--no-monochrome` (optional, default: `true`) — Enable RGB Mixer Monochrome mode
- `--preserve-luminance/--no-preserve-luminance` (optional, default: `true`) — Preserve luminance while monochrome is enabled
- `--red` (optional) — Requested RGB Mixer red coefficient; currently returns an explicit unsupported diagnostic
- `--green` (optional) — Requested RGB Mixer green coefficient; currently returns an explicit unsupported diagnostic
- `--blue` (optional) — Requested RGB Mixer blue coefficient; currently returns an explicit unsupported diagnostic

## Boundaries and gotchas

- The supplied numbers are only echoed, not applied.
- Dry-run's generic message does not reveal this coercion or the selected node.
- Duplicate clip names can make name-only targeting ambiguous.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page rgb-mixer-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
