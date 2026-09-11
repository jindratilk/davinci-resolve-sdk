# `clip marker delete-custom`

Syntax: `cutagent clip marker delete-custom CLIP_OR_DATA [MAYBE_DATA] [--clip VALUE]`

## Search terms

- delete marker by custom data
- remove tagged clip marker
- delete source marker by token
- erase marker with hidden identifier
- remove automation marker safely
- delete customData marker
- clean tagged clip annotation
- remove marker without frame

## What it does

Delete a marker by custom data.

## Do not use when

Use `clip marker delete` when the source frame is known and custom data is absent or not unique. Do not use this as a global cleanup across clips; it targets one item.

## Preflight and readback

Run `get-custom` on the same item/token and preserve returned metadata, then list the item to know the initial marker count.

## Public arguments and options

- `CLIP_OR_DATA` (required) — Clip name or custom marker data
- `MAYBE_DATA` (optional) — Custom marker data when clip is positional
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- A true result is not followed by marker-map readback, so explicit verification is required.
- Positional parsing changes with argument count: two arguments mean clip + data, while one means data with `--clip` or current item.
- The command has a dry-run path, but dry-run does not resolve the clip or confirm token existence.

## Examples

- `cutagent clip marker delete-custom --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
