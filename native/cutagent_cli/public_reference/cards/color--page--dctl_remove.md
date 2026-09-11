# `color page dctl-remove`

Syntax: `cutagent color page dctl-remove [--clip VALUE] [--node VALUE]`

## Search terms

- remove DCTL
- clear node transform
- detach DCTL from Color node
- remove node LUT
- disable custom color transform
- restore node without DCTL
- take LUT off grade node

## What it does

Runs the public `color page dctl-remove` CutAgent command.

## Do not use when

Use `color page resolvefx-remove` for a DCTL/other effect represented as a ResolveFX tool, `color page dctl-apply` to replace the current slot with another transform, and node enable/disable when the entire grade node should be bypassed temporarily. Do not use this command merely because a tool is called “DCTL” in the GUI without first confirming `color node lut-get` reports it in the node LUT slot.

## Preflight and readback

If the node still contains a similarly named ResolveFX tool, remove that tool through the ResolveFX family instead.

## Public arguments and options

- `--clip` (optional) — Clip name; defaults to current Color page clip
- `--node` (optional, default: `1`) — Color node index

## Boundaries and gotchas

- The command cannot distinguish “DCTL” provenance at removal time.
- Clearing is destructive to the previous assignment and the command does not return a restorable copy of that key; capture it before running.
- Dry-run cannot tell whether the node currently has a transform, so it does not distinguish a meaningful removal from an idempotent no-op.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page dctl-remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
