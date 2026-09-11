# `color page dctl-apply`

Syntax: `cutagent color page dctl-apply NAME [--clip VALUE] [--node VALUE]`

## Search terms

- apply DCTL
- add DCTL to Color node
- load transform script
- apply display transform
- use custom color transform
- set node DCTL
- apply LUT through DCTL command
- install and use cube on node

## What it does

Runs the public `color page dctl-apply` CutAgent command.

## Do not use when

Use `dctl-remove`/`color lut --clear` to clear the slot.

## Preflight and readback

Before running, confirm the exact clip/node, inspect `color node lut-get`, ensure the DCTL/LUT is installed or the source path is readable, and save any existing assignment for restoration. Use a frame where the transform visibly changes pixels. If proof fails, manually decide whether to clear/restore the previous LUT because the command does not roll the node back.

## Public arguments and options

- `NAME` (required) — DCTL/LUT name or path
- `--clip` (optional) — Clip name; defaults to current Color page clip
- `--node` (optional, default: `1`) — Color node index

## Boundaries and gotchas

- Proof is deliberately two-layered: a Color-page still must change and a temporary one-frame Deliver render must also change.
- Dry-run validates only nonempty name, node and clip text.
- It does not establish file existence, library acceptance, readback key or visual effect.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page dctl-apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
