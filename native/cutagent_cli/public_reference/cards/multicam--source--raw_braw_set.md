# `multicam source raw-braw-set`

Syntax: `cutagent multicam source raw-braw-set --angle VALUE --record-frame VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--settings-json VALUE] [--iso VALUE] [--exposure VALUE] [--white-balance-kelvin VALUE] [--white-balance-tint VALUE]`

## Search terms

- multicam Blackmagic RAW
- BRAW sidecar
- per angle raw settings
- white balance raw clip

## What it does

Change Blackmagic RAW settings inside a multicam angle.

## Do not use when

Do not use on non-BRAW media. Do not assume every sidecar key is accepted under every decode profile. Do not bypass canonical readback or leave a rejected sidecar in place.

## Preflight and readback

Back up existing sidecar and record source timecode.

## Public arguments and options

- `--angle` (required)
- `--record-frame` (required) — Frame relative to the multicam start inside the desired source item
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--settings-json` (optional) — BRAW SDK sidecar JSON patch for any persistent RAW processing key
- `--iso` (optional) — Per-frame Blackmagic RAW ISO
- `--exposure` (optional) — Per-frame Blackmagic RAW exposure in stops
- `--white-balance-kelvin` (optional)
- `--white-balance-tint` (optional)

## Boundaries and gotchas

- Typed options include ISO, exposure, white-balance Kelvin, and tint; `--settings-json` accepts other persistent SDK keys.

## Examples

- `cutagent multicam source raw-braw-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
