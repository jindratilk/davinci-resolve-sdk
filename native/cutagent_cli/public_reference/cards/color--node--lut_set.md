# `color node lut-set`

Syntax: `cutagent color node lut-set NODE_INDEX LUT_PATH [--clip VALUE] [--node-stack-layer VALUE]`

## Search terms

- set LUT on Color node
- apply cube LUT to grade node
- assign LUT library key
- load local LUT into node
- add look LUT to clip node
- install and apply LUT file
- change node LUT transform

## What it does

Set LUT on a color node.

## Do not use when

Use LUT-library import for installing a collection without assigning it, `color export-lut` to generate a cube, and grade/CDL commands when a primary correction rather than a LUT transform is intended.

## Preflight and readback

Preserve the prior key so it can be restored; clearing the node will not uninstall copied files.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based node index
- `LUT_PATH` (required) — LUT path
- `--clip` (optional) — Clip name (current clip when omitted)
- `--node-stack-layer` (optional, default: `1`) — One-based node-stack layer index

## Boundaries and gotchas

- That system artifact survives node clear/reset and must be managed separately.
- The response is only a success message containing the requested string.
- A matching key does not prove the node is enabled or the visual transform is correct.
- There is no command-specific dry-run branch and no empty-string clear path.
- Node indices are validated against the current one-based graph before setting.

## Examples

- `cutagent color node lut-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
