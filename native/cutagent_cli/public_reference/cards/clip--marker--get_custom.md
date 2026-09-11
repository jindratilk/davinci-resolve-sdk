# `clip marker get-custom`

Syntax: `cutagent clip marker get-custom CLIP_OR_DATA [MAYBE_DATA] [--clip VALUE]`

## Search terms

- find marker by custom data
- look up clip marker token
- retrieve marker by hidden identifier
- resolve customData marker
- check marker automation tag
- find tagged source marker

## What it does

Read a marker by custom data.

## Do not use when

Use `clip marker list` when you know a frame or need source/offset/record mapping. Do not use this to search marker name/note text; custom data is a separate hidden field. Do not treat it as a cross-timeline/global token search—the command queries only one resolved item.

## Preflight and readback

Identify the exact item and token, then query using either `CLIP DATA` or `DATA --clip CLIP`. Use it immediately after `custom-data` to verify attachment and before `delete-custom` to capture visible metadata for audit/restoration.

## Public arguments and options

- `CLIP_OR_DATA` (required) — Clip name or custom marker data
- `MAYBE_DATA` (optional) — Custom marker data when clip is positional
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- The marker object does not include its frame, offset, or record position.
- Pair with `clip marker list` if location is required.
- Token comparison and duplicate-token behavior are delegated to DaVinci Resolve; the command does not normalize strings or detect ambiguity.
- With two positional arguments the first becomes clip name; with one argument it becomes data and `--clip`/current item determines target.

## Examples

- `cutagent clip marker get-custom --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
