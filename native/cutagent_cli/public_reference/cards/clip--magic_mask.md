# `clip magic-mask`

Syntax: `cutagent clip magic-mask [NAME] [--mode VALUE] [--regenerate] [--track VALUE] [--record-frame VALUE]`

## Search terms

- create Magic Mask on clip
- isolate person with AI mask
- regenerate Magic Mask
- make foreground matte in DaVinci Resolve
- Color page neural mask
- check Magic Mask CLI availability

## What it does

Check Magic Mask availability.

## Do not use when

Do not use this command to promise or perform any mask operation: every valid invocation is intentionally blocked. Use Fusion polygon/bitmap masks when deterministic manual geometry is appropriate, and qualifier/window commands when color/luma/spatial isolation—not neural subject recognition—solves the request.

## Preflight and readback

Before considering this command, check edition and decide whether a manual Color-page or Fusion route is acceptable. Calling it needs no project preflight because it cannot mutate. If using an alternative supervised workflow, verify foreground-only and all-layers frames separately.

## Public arguments and options

- `NAME` (optional) — Clip name (or current clip)
- `--mode` (optional, default: `"bi"`) — Mask direction: f, b, or bi
- `--regenerate` (optional, default: `false`) — Regenerate an existing magic mask
- `--track` (optional) — Video track index for deterministic clip selection
- `--record-frame/--at` (optional) — Record-domain frame/time inside the target clip

## Boundaries and gotchas

- `--regenerate` cannot inspect whether a mask already exists.

## DaVinci Resolve editions

The supervised GUI caveat is Studio-oriented and is not a public CutAgent CLI route.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent clip magic-mask --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
