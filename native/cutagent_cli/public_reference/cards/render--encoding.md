# `render encoding`

Syntax: `cutagent render encoding --profile VALUE [--multi-pass] [--network-optimization]`

## Search terms

- configure render encoding flags
- EncodingProfile setting
- MultiPassEncode setting
- NetworkOptimization setting
- enable multi pass render
- network optimized encoding
- encoding profile Main High
- Deliver encoding options

## What it does

Configure common encoding flags.

## Do not use when

Do not use without confirming the active format/codec supports the profile and flags. The command does not enumerate or validate compatible values.
Do not use only to change the profile if current multi-pass or network-optimization values must remain unchanged; omitted switches default to false and are still written.
Do not pass an empty, guessed, or differently cased profile unless the connected DaVinci Resolve route is known to accept it.
Do not treat command success as readback verification or rendered-output validation.

## Preflight and readback

Before execution, capture current render settings, format/codec, and the exact profile/flag combinations exposed by the Deliver page for that route.
Specify all three intended values explicitly, even when one is false. Use dry-run to inspect the complete dictionary that would be sent.
Add and render a short test, then inspect codec profile, pass behavior, and streaming/network metadata with an independent media analyzer.

## Public arguments and options

- `--profile` (required) — Encoding profile name/value
- `--multi-pass/--single-pass` (optional, default: `false`) — Enable multi-pass encoding
- `--network-optimization/--no-network-optimization` (optional, default: `false`) — Enable network optimization

## Boundaries and gotchas

- Exact help is `cutagent render encoding --profile TEXT [OPTIONS]`.
- `--profile` is required syntactically.
- Multi-pass defaults to false (`--single-pass` behavior).

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `MISSING_ARGUMENT`

## Examples

- `cutagent render encoding --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
