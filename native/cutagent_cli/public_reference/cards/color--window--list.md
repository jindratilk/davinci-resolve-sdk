# `color window list`

Syntax: `cutagent color window list [--clip VALUE] [--comp VALUE]`

## Search terms

- list Fusion windows
- show clip masks
- enumerate grading windows
- find ellipse mask name
- inspect rectangle ellipse polygon tools
- list ColorCorrector mask helpers
- see windows in Fusion comp
- find window before attach detach
- inventory clip-attached masks
- show grading mask tool names
- check available window tools

## What it does

List clip-attached Fusion windows and masks.

## Do not use when

Use `color mask inspect` when active-chain order, connected/orphan status, primary, qualifiers, trackers or main output wiring is needed. Use Fusion comp export/tool inspection for Center/Width/Height/SoftEdge, polygon points, keyframes or combine settings; window list returns no geometry. Use `window attach`, `detach` or `reorder` only after the desired tool/state is unambiguous.
Use broader Fusion tool listing when a mask-like tool of another registered type is relevant.

## Preflight and readback

Before listing, confirm the project/timeline and either pass the exact clip name or deliberately position the playhead. Choose the 1-based comp index; the command will not create a missing comp. If repeated timeline items share a name, use timeline occurrence evidence first because there is no track/frame selector.
Afterward, retain names/types/shapes but do not interpret row order as stack order. Run `color mask inspect` to mark each row active versus orphaned and get actual chain order, then export the comp when geometry matters.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- With no `--clip`, output does not identify which current item was resolved.
- `--comp` is 1-based.
- Global `--dry-run` has no special preview branch.
- It does not validate graph health.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color window list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
