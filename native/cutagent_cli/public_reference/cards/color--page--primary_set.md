# `color page primary-set`

Syntax: `cutagent color page primary-set [CLIP_NAME] [--track VALUE] [--at VALUE] [--node-index VALUE] [--contrast VALUE] [--pivot VALUE] [--temperature VALUE] [--tint VALUE] [--hue VALUE] [--lum-mix VALUE] [--highlights VALUE] [--shadows VALUE] [--color-boost VALUE] [--mid-detail VALUE] [--offset-r VALUE] [--offset-g VALUE] [--offset-b VALUE] [--require-render-proof]`

## Search terms

- set primary grade by node index
- set primary highlights and shadows
- adjust color boost or midtone detail
- deterministic Color node primaries
- grade a clip without GUI automation
- set hue and luminance mix on a node

## What it does

Set Color Page primary controls using project readback (Disk projects only).

## Preflight and readback

Before mutation, confirm that the project is a local Disk project, save it, identify the exact timeline item (duplicate clip names need disambiguation before invoking this name-only surface), inspect the active grade version and node graph, and capture a grade/checkpoint plus a reference frame. For node 2+, ensure that node already exists and produces or can produce a measurable image change. Then inspect the Color page values and image.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name
- `--track` (optional) — Exact 1-based video track selector
- `--at` (optional) — Exact timeline position selector
- `--node-index/--node` (optional, default: `1`) — 1-based Color Page node index
- `--contrast` (optional) — Primary contrast value
- `--pivot` (optional) — Primary pivot value
- `--temperature` (optional) — Primary temperature value
- `--tint` (optional) — Primary tint value
- `--hue` (optional) — Primary hue value
- `--lum-mix` (optional) — Luminance mix value
- `--highlights` (optional) — Primary highlights value
- `--shadows` (optional) — Primary shadows value
- `--color-boost` (optional) — Primary color boost value
- `--mid-detail` (optional) — Primary midtone detail value
- `--offset-r` (optional) — Offset Red
- `--offset-g` (optional) — Offset Green
- `--offset-b` (optional) — Offset Blue
- `--require-render-proof` (optional, default: `false`) — Export before/after Color Page frames and fail unless the rendered image changes

## Boundaries and gotchas

- Never rely on zero-based indexing.
- That recovery itself must be checked against the real reopened project/timeline; a returned failure is not sufficient evidence that the application state is safe.

## Examples

- `cutagent color page primary-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
