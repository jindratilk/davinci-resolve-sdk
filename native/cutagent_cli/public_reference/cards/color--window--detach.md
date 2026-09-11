# `color window detach`

Syntax: `cutagent color window detach WINDOW_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- detach Fusion window
- remove mask from active chain
- disable rectangle grading mask
- disconnect ellipse from ColorCorrector
- orphan polygon window without deleting it
- bypass one Fusion window
- take window out of mask stack
- stop window affecting grade
- preserve mask tool but disconnect it
- remove active grading window

## What it does

Detach a window from the active mask chain.

## Do not use when

Use `color window attach` to activate an orphaned window, `window reorder` to move active windows, and the window creation commands when a new shape is needed. Use Fusion tool deletion only when the mask object and its geometry/keyframes should be destroyed; detach deliberately preserves them. Use `color tracker attach-window` when changing the relationship between a named window and tracker rather than removing a window from the global active chain.
Do not use it as a harmless bypass in a custom main image graph: canonicalization can disconnect noncanonical main-chain tools.

## Preflight and readback

Treat an orphan warning as the expected representation of a preserved detached tool, not deletion. Inspect main-chain wiring and render/export a frame or mask view.

## Public arguments and options

- `WINDOW_NAME` (required) — Window tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Detach does not delete the window.
- Only helpers present in the pre-chain are retained.
- Unlike attach, detach does not automatically include every orphaned qualifier/tracker in the comp.
- Both occur after acquiring/snapshotting the comp and can take much longer than validation-only dry-run.
- Specialized connections can be lost even though only one window was requested for detachment.
- Graph validation permits orphan warnings in non-strict mode, so `valid:true` does not mean no orphaned tools or unchanged image.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color window detach --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
