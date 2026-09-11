# `color window attach`

Syntax: `cutagent color window attach WINDOW_NAME [--clip VALUE] [--position VALUE] [--comp VALUE]`

## Search terms

- attach Fusion grading window
- add mask to active chain
- reconnect orphaned rectangle mask
- put window in mask stack
- activate ellipse mask for color correction
- connect polygon window to primary
- reorder window while attaching
- feed window into ColorCorrector mask
- enable clip Fusion mask
- rebuild grading mask chain
- connect all mask helpers

## What it does

Attach a window into the active mask chain.

## Do not use when

Use `color window rectangle`, `ellipse` or `polygon` when the shape tool does not yet exist; attach never creates the requested window. Use `color window reorder` when the active window stack already contains the correct tools and only order should change, and `window detach` to remove one from the active chain.
Do not use it in a comp with a custom main image graph that must be preserved: canonicalization reconnects MediaIn directly to the first ColorCorrector and that tool directly to MediaOut. Do not assume a color-version duplicate protects this edit; Fusion comp wiring is separate from Color-page version state.

## Preflight and readback

Confirm the requested name is an existing supported mask type and choose the comp index. Export the Fusion comp or duplicate the timeline test item; a Color version alone is not sufficient.
Run `color mask inspect` independently to ensure no unexpected orphan/reactivation and inspect the main output source.

## Public arguments and options

- `WINDOW_NAME` (required) — Window tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--position` (optional) — 0-based stack position
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Attaching one window includes all window, qualifier and tracker helpers found anywhere in the comp, not only currently active tools.
- `--position` moves the target only within the window subsection; it cannot place a window after a qualifier/tracker.
- Oversized positions do not fail.
- Dry-run is unresolved: it does not check clip, comp, window type/name, current graph or the eventual clamped position.
- If multiple exist, only the first discovered is primary; extra primaries are not incorporated into the canonical main path.
- Index validation and out-of-range comp errors are separate.
- The command does not explicitly save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent color window attach --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
