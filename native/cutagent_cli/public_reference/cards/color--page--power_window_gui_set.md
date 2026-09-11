# `color page power-window-gui-set`

Syntax: `cutagent color page power-window-gui-set [CLIP_NAME] [--shape VALUE] [--size VALUE] [--aspect VALUE] [--pan VALUE] [--tilt VALUE] [--rotate VALUE] [--opacity VALUE] [--soft-1 VALUE] [--soft-2 VALUE] [--soft-3 VALUE] [--soft-4 VALUE] [--inside VALUE] [--outside VALUE] [--invert] [--expected-node-index VALUE]`

## Search terms

- create Power Window through GUI
- set window size and aspect
- rotate Power Window
- edit Color window controls
- create circle mask in GUI
- create rectangle mask in GUI
- create polygon Power Window
- adjust window feather controls
- set selected node window

## What it does

Create and select and transform a Color Page Power Window through the custom edit-owned interface.

## Do not use when

Use `power-window-track` for tracker execution, and a node-local grade command for visible effect/locality proof.

## Preflight and readback

Record the node graph and render/matte reference. Confirm the Window palette and requested numeric fields exist for that shape. Undo/remove the window manually if any late proof or semantic check fails.

## Public arguments and options

- `CLIP_NAME` (optional) — Clip name; defaults to current Color page clip
- `--shape` (optional, default: `"linear"`) — Power Window shape button to create/select
- `--size` (optional) — Window Size GUI value, 0..100
- `--aspect` (optional) — Window Aspect GUI value, 0..100
- `--pan` (optional) — Window Pan GUI value, 0..100
- `--tilt` (optional) — Window Tilt GUI value, 0..100
- `--rotate` (optional) — Window Rotate GUI value, -180..180
- `--opacity` (optional) — Window Opacity GUI value, 0..100
- `--soft-1` (optional) — Window Soft 1 GUI value, 0..100
- `--soft-2` (optional) — Window Soft 2 GUI value, 0..100
- `--soft-3` (optional) — Window Soft 3 GUI value, 0..100
- `--soft-4` (optional) — Window Soft 4 GUI value, 0..100
- `--inside` (optional) — Window Inside GUI value, 0..100
- `--outside` (optional) — Window Outside GUI value, 0..100
- `--invert/--no-invert` (optional)
- `--expected-node-index/--expect-node` (optional) — Fail unless this node reads back with Power Windows

## Boundaries and gotchas

- `--expected-node-index` is only an assertion against graph readback.
- If the GUI selected node differs, the mutation happens there and the command may fail only after changing it.
- This does not prove the controls went to the intended node.
- All normalized controls are range-checked and finite, but only labels actually exposed for the current shape/panel can be typed.
- The route is macOS-only in practice and needs Accessibility, Screen Recording, a visible DaVinci Resolve window, no blocking permission dialog, and a usable Color Window palette.
- The screenshot and node-graph tool presence are setup proof only.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent color page power-window-gui-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
