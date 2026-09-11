# `color page read`

Syntax: `cutagent color page read [CLIP_NAME]`

## Search terms

- inspect lift gamma gain saturation
- list clip grade versions
- decode Color node parameters
- check whether clip has correction
- inspect all versions for clip name

## What it does

Read color grade params from the project (Lift and Gamma and Gain and Saturation).

## Do not use when

Use a mutation command's own post-reopen verifier when exact target identity matters; `color page read` groups by name and does not map results back to one timeline occurrence. Do not use this command to infer which version is active: it lists all linked versions without an active marker.

## Preflight and readback

Before reading, save the project if current GUI changes must be represented on disk, identify the timeline/track/record position and note whether duplicate clip names exist. Treat per-version `error` fields as decode failures even when the overall command succeeds. Compare exact raw parameter keys/types/node indices rather than assuming omitted parameters equal a displayed GUI default.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name (None = current)

## Boundaries and gotchas

- Do not infer mutation or wheel-only scope from those metadata fields.

## Examples

- `cutagent color page read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
