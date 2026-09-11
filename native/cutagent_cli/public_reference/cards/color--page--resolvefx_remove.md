# `color page resolvefx-remove`

Syntax: `cutagent color page resolvefx-remove [CLIP_NAME] [--node-index VALUE]`

## Search terms

- remove ResolveFX from Color node
- clear Box Blur from grade node
- disable by removing ResolveFX
- strip Color page plugin block
- remove current node effect
- delete OFX without deleting node

## What it does

Runs the public `color page resolvefx-remove` CutAgent command.

## Do not use when

Use `resolvefx-add` to replace the current effect with another. Use Fusion tool deletion commands when the effect is inside a Fusion composition rather than the Color-page ResolveFX block.

## Preflight and readback

Before mutation, run `resolvefx-param-list` on the exact clip/node, save the plugin ID and option values or a grade checkpoint, and confirm local Disk/embedded close-reopen readiness. After reopen, inspect node/version/clip identity, `removed: true`, null plugin ID and readback tool keys/options; visually confirm the effect disappeared while the node and other corrections remain.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index containing the ResolveFX OFX tool

## Boundaries and gotchas

- It does not create a grade merely to remove nothing.
- Duplicate clip names and stale node numbering can target the wrong grade container.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color page resolvefx-remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
