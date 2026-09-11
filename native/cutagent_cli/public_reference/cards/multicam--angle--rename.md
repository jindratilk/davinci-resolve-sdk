# `multicam angle rename`

Syntax: `cutagent multicam angle rename --angle VALUE --name VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--media-type VALUE]`

## Search terms

- multicam angle rename
- Rename a multicam angle.
- multicam angle rename help
- multicam angle rename command

## What it does

Rename a multicam angle.

## Do not use when

Do not use a zero-based angle number. Do not rename only one media type accidentally when linked angle naming is intended. Use reorder separately when changing angle order.

## Preflight and readback

Inspect angle names and enable states first. After mutation verify both requested track names and unchanged item IDs/timing after reopen.

## Public arguments and options

- `--angle` (required)
- `--name` (required) — New persistent angle track name
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--media-type` (optional, default: `"both"`) — both, video, or audio

## Boundaries and gotchas

- `--angle` is one-based and `--name` cannot be empty.

## Examples

- `cutagent multicam angle rename --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
