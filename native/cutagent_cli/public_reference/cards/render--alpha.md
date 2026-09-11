# `render alpha`

Syntax: `cutagent render alpha [--enable] [--mode VALUE]`

## Search terms

- enable render alpha channel
- AlphaMode premultiplied
- straight alpha export
- QuickTime alpha render
- transparent video export
- render format alpha support
- disable alpha no-op

## What it does

Configure alpha-channel export settings.

## Do not use when

Do not assume verification status proves rendered transparency.

## Preflight and readback

Before execution, capture current render format/codec/settings, output target/name, alpha expectations (straight versus premultiplied), and downstream application requirements.
Render a short transparency test and inspect alpha in a trusted application.

## Public arguments and options

- `--enable/--disable` (optional, default: `true`) — Enable or disable alpha export
- `--mode` (optional, default: `"premultiplied"`) — premultiplied|straight

## Boundaries and gotchas

- Exact help is `cutagent render alpha [--enable|--disable] [--mode premultiplied|straight]`.
- Command-level mode validation is exact and case-sensitive.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent render alpha --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
