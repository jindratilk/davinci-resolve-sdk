# `storage matte add`

Syntax: `cutagent storage matte add CLIP PATHS... [--eye VALUE]`

## Search terms

- add clip matte
- Media Pool clip matte
- stereo left right matte
- attach external matte files
- storage import matte
- multiple matte paths

## What it does

Add matte files to a media pool clip.

## Do not use when

Do not attach mattes before disambiguating duplicate clip names and making the intended Media Pool folder current.

## Preflight and readback

Use dry-run to verify count and clip spelling only; separately verify every path and eye value.
Remove unintended mattes manually.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name
- `PATHS` (required, repeatable) — Matte file paths
- `--eye` (optional) — Stereo eye: left or right

## Boundaries and gotchas

- At least one positional matte path is required by the CLI.
- Dry-run does not echo paths or eye.
- Clip name matching is exact and case-sensitive.
- If the current folder contains matches, the first matching clip wins without checking duplicate names elsewhere.

## Stable public error codes

- `API_CALL_FAILED`
- `CAPABILITY_NEGOTIATION_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`
- `VALIDATION_ERROR`

## Examples

- `cutagent storage matte add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
