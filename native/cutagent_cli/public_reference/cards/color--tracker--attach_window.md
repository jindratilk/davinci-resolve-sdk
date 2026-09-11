# `color tracker attach-window`

Syntax: `cutagent color tracker attach-window TRACKER_NAME WINDOW_NAME [--clip VALUE] [--comp VALUE]`

## Search terms

- attach window to tracker
- connect mask to motion tracker
- track a rectangle mask
- track an ellipse window
- feed power window into Fusion Tracker
- put mask before tracker
- make window feed tracked grade
- wire RectangleMask to Tracker foreground
- combine grading window and tracker
- attach polygon mask to existing tracker
- connect tracked Fusion mask

## What it does

Ensure a window feeds the tracked mask chain.

## Do not use when

Use `color window rectangle`, `ellipse`, or `polygon` to create the window first, and `color tracker add` to create the Tracker. Use `color tracker attach-qualifier` when the upstream matte is a ChromaKeyer rather than a geometric window. Use `color window attach` to include/reorder a window in the general canonical mask stack without forcing one Tracker to become the direct primary mask source. Use `color secondary tracked-window` for a new window-plus-tracker scaffold.

## Preflight and readback

Verify the exact window type/name and Tracker resolution, and checkpoint valuable custom routing. Confirm the window geometry visually and the intended frame/target separately; this operation does not calculate either.
Treat any new orphan warning as a behavior change requiring repair or explicit acceptance. Verify that prior qualifiers and other trackers remain part of the intended mask; the command can bypass them. Then run tracking separately, inspect track/keyframe data and render/frame-export several frames to prove the window follows the desired subject.

## Public arguments and options

- `TRACKER_NAME` (required) — Tracker tool name
- `WINDOW_NAME` (required) — Window tool name
- `--clip` (optional) — Clip name (current clip when omitted)
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Looking only at their own inputs can falsely suggest they remain active.
- “Attach” does not animate or geometrically link the mask.
- The Tracker can contain only initial/default points and the window stays static until a separate tracking workflow succeeds.
- The code connects MediaIn only to the target Tracker and primary, and does not normalize other tools' image inputs.
- The named window must be exactly one of CutAgent's supported Fusion mask tool types.
- Structural validation follows the active chain and checks required image inputs, but allows orphan warnings and does not check tracking samples, mask motion, matte pixels, requested source preservation, or visual output.
- Dry-run validates only nonblank arguments and positive comp index.
- It does not resolve the clip, comp, Tracker/window, inspect current upstream, predict orphans, or show the resulting chain.
- Clip selection is by current item or name only, with no track/record-frame disambiguator.
- Duplicate clip names require external confirmation.

## Examples

- `cutagent color tracker attach-window --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
