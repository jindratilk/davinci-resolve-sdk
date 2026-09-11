# `color tracker add`

Syntax: `cutagent color tracker add [--clip VALUE] [--pattern-center VALUE] [--comp VALUE]`

## Search terms

- add Fusion tracker
- create tracker on clip
- track a subject in grading comp
- add motion tracker target
- create IntelliTrack point
- put tracker in effect mask chain
- track a power window setup
- initialize tracking point
- add tracker at screen position
- attach motion tracker to ColorCorrector mask
- create tracking scaffold

## What it does

Add a Fusion tracker to the clip grading comp.

## Do not use when

Use `color tracker set-target` to move an existing tracker point instead of adding another Tracker tool. Use `color tracker attach-window` or `attach-qualifier` when an already-created window/qualifier must be included in the tracked mask chain. Use `color secondary tracked-window` when the intended operation is to create both a new rectangle/ellipse and tracker together, or `color secondary subject-isolation` for its fixed ellipse-plus-tracker scaffold. Do not add another tracker merely to change the target position or repair an orphaned graph—use `set-target` or `color comp repair` as appropriate.

## Preflight and readback

Before running, identify the timeline/clip unambiguously, list its Fusion comp count, run `color tracker list`, and inspect/export the full comp graph. Confirm the intended `--comp` and note that the current command cannot disambiguate duplicate clip names by track/frame. Check whether the graph contains hand-built Fusion tools: canonicalization can change their connections.
Compare the pre/post graph for reordering or displaced custom connections and render/frame-export representative frames if the mask controls a visible grade.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--pattern-center` (optional, default: `"0.5,0.5"`) — Initial pattern center X,Y
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- Agents must inspect/delete/configure unintended points before tracking.
- X and Y are only required to be finite numbers.
- Canonicalization includes every supported window, ChromaKeyer and Tracker found in the composition, not only CutAgent-created tools.
- A connected window may flow through the Tracker's foreground/matte topology, but the command does not bind window center to tracked coordinates.
- If no comp exists, `--comp 1` can create one.
- Higher requested indices fail against the pre-existing comp count; the command cannot create comp 2 or later.
- The output does not report comp index/count, making post-inspection important.
- `--clip` resolves by name across the current timeline and offers no track/record-frame selector.
- Dry-run validates clip text, center syntax/finite values and comp positivity, but does not connect or resolve the clip/comp.

## Examples

- `cutagent color tracker add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
