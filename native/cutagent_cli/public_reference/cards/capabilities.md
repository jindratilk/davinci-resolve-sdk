# `capabilities`

Syntax: `cutagent capabilities [FEATURE_ID] [--full]`

## Search terms

- is this CutAgent feature supported
- Studio Free feature parity
- unsupported DaVinci Resolve automation
- feature caveats and limits
- verification requirement for command
- CutAgent feature graph

## What it does

Check available DaVinci Resolve features.

## Do not use when

Do not use `capabilities` to prove that DaVinci Resolve is connected or that the intended project is open; use `status`.

## Preflight and readback

Query the exact feature id rather than loading the entire graph when only one decision is needed. After the actual operation, do not rerun `capabilities` as verification - run the feature's state readback and any required render/GUI proof.

## Public arguments and options

- `FEATURE_ID` (optional) — Optional capability/feature id lookup
- `--full` (optional, default: `false`)

## Boundaries and gotchas

- `supported` means the declared route is available for its documented scope, not that every DaVinci Resolve UI variant or parameter is controllable.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent capabilities --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
