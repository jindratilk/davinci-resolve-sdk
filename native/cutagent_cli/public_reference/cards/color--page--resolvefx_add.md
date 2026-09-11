# `color page resolvefx-add`

Syntax: `cutagent color page resolvefx-add [CLIP_NAME] [--node-index VALUE] --fx VALUE`

## Search terms

- add ResolveFX to Color node
- add Box Blur to grade node
- apply ResolveFX Vignette
- put Glow effect on Color page node
- attach installed ResolveFX by plugin ID
- create default ResolveFX instance
- replace ResolveFX on node

## What it does

Runs the public `color page resolvefx-add` CutAgent command.

## Do not use when

Use `resolvefx-remove` to clear the current ResolveFX block. Do not target node 2+ until that Color node exists.

## Preflight and readback

Before mutation, run `resolvefx-list`, record the exact plugin ID/category and Studio/Free availability, inspect the target node with `resolvefx-param-list`/grade readback, and checkpoint the grade because any existing ResolveFX on that node will be replaced. Confirm a local Disk project and a reliable embedded close/reopen path.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index to receive the ResolveFX OFX tool
- `--fx` (required) — ResolveFX name or plugin id (e.g. vignette, box-blur, com.blackmagicdesign.resolvefx.glow)

## Boundaries and gotchas

- It does not run per-invocation rendered-frame proof, so an unavailable/ignored plugin can still pass byte readback.
- All documentation/workflows must use 1-based indices.
- Duplicate clip names require prior target disambiguation; the public surface exposes name or current clip, not track/frame selectors.

## DaVinci Resolve editions

Before mutation, run `resolvefx-list`, record the exact plugin ID/category and Studio/Free availability, inspect the target node with `resolvefx-param-list`/grade readback, and checkpoint the grade because any existing ResolveFX on that node will be replaced.
External scripting connections can break during this lifecycle; verify the intended project/timeline after reopen. - Duplicate clip names require prior target disambiguation; the public surface exposes name or current clip, not track/frame selectors. - Default ResolveFX behavior and availability can differ between DaVinci Resolve Studio and Free.

## Examples

- `cutagent color page resolvefx-add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
