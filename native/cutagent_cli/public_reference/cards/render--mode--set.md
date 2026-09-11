# `render mode set`

Syntax: `cutagent render mode set MODE`

## Search terms

- set render mode
- individual clips mode
- single clip mode
- mode 0 individual
- mode 1 single
- Deliver render segmentation
- change render output mode

## What it does

Set render mode.

## Do not use when

Do not change mode without understanding its effect on output segmentation, naming, handles, and downstream deliverable expectations.
Do not pass surrounding whitespace or other synonyms.
Do not set mode while another workflow is concurrently configuring Deliver settings without coordinating the shared project state.

## Preflight and readback

Before execution, run `render mode get`, capture current Deliver settings and queue, and determine whether the deliverable requires individual clips or one single clip.
Use dry-run to verify normalized value `0` or `1`.
Inspect the Deliver page and queue/render a safe sample to verify segmentation and naming behavior.

## Public arguments and options

- `MODE` (required) — Render mode: individual (0) or single (1)

## Boundaries and gotchas

- Accepted individual values are case-insensitive `individual` and exact string `0`.
- Accepted single values are case-insensitive `single` and exact string `1`.
- The command does not explicitly open the Deliver page.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render mode set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
