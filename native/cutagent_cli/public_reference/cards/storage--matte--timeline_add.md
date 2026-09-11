# `storage matte timeline-add`

Syntax: `cutagent storage matte timeline-add PATHS...`

## Search terms

- add timeline matte
- DaVinci Resolve timeline matte
- Media Pool timeline matte import
- multiple timeline matte paths

## What it does

Add timeline matte files to the media pool.

## Do not use when

Do not use clip mattes and timeline mattes interchangeably; clip-specific mattes use `storage matte add`.

## Preflight and readback

Before execution, inspect every matte file, confirm the intended active project/timeline and timeline-matte semantics, capture existing mattes, and use dry-run to verify count.
Ensure the embedded bridge/auth environment is available to the child process and keep paths free of sensitive information where process-list visibility matters.
After success or crash, inspect Media Pool/timeline matte state and rendered output before retrying. Compare returned item names/count, and manually remove duplicates or partial additions.

## Public arguments and options

- `PATHS` (required, repeatable) — Timeline matte file paths

## Boundaries and gotchas

- At least one positional path is required by CLI parsing.
- Dry-run does not echo or validate paths.
- Parent attempts to parse status JSON only when the file exists.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent storage matte timeline-add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
