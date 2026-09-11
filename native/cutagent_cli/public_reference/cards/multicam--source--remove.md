# `multicam source remove`

Syntax: `cutagent multicam source remove --angle VALUE --item-index VALUE [--multicam-name VALUE] [--media-id VALUE] [--sequence-id VALUE] [--media-type VALUE] [--force]`

## Search terms

- multicam source remove
- Remove a source item from a multicam angle.
- multicam source remove help
- multicam source remove command

## What it does

Remove a source item from a multicam angle.

## Do not use when

Do not remove a whole angle with this command. Do not identify a repeated clip only by name; inspect and use its item index. Avoid a one-sided media-type removal unless the asymmetry is intended.

## Preflight and readback

Inspect item IDs and index order, checkpoint, and dry-run. After execution require only the selected item pair to be absent, later indices contiguous, other identities/timing unchanged, and reopen persistence.

## Public arguments and options

- `--angle` (required)
- `--item-index` (required) — Zero-based source item index within the angle
- `--multicam-name` (optional)
- `--media-id` (optional)
- `--sequence-id` (optional)
- `--media-type` (optional, default: `"both"`) — both, video, or audio
- `--force/-f` (optional, default: `false`) — Confirm source item removal

## Boundaries and gotchas

- `--item-index` is zero-based and `--angle` is one-based.
- `--media-type` defaults to `both`.

## Examples

- `cutagent multicam source remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
