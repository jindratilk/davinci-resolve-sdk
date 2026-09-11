# `color arri-cdl-lut`

Syntax: `cutagent color arri-cdl-lut [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- apply ARRI CDL metadata
- use ARRI embedded look
- interpret ARRI clip color metadata
- apply ARRI LogC look metadata

## What it does

Apply ARRI CDL and LUT color adjustments.

## Do not use when

Use `color cdl set` when explicit ASC CDL slope/offset/power/saturation values are known, `color lut` when applying a chosen LUT file to a known node, and `color grade-apply` for a DRX grade. Use Color Space Transform commands for a deliberate LogC-to-working-space transform.

## Preflight and readback

Before execution, confirm the target item and inspect `color nodes CLIP`, source camera metadata, and existing grade. Dry-run records only the target.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Examples

- `cutagent color arri-cdl-lut --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
