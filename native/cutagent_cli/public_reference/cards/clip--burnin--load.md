# `clip burnin load`

Syntax: `cutagent clip burnin load CLIP_OR_NAME [MAYBE_NAME] [--clip VALUE]`

## Search terms

- apply burn-in preset to one timeline clip
- set clip-specific data burn-in
- add timecode overlay to selected edit
- load watermark on timeline item
- per-clip slate overlay preset
- apply metadata burn-in to named occurrence
- set clip burn-in before render
- load saved overlay on current clip

## What it does

Load a burn-in preset on a timeline item.

## Do not use when

Use `render burnin load`/`burnin load` when one preset should govern the project/render context, not one occurrence. Use `render burnin import` or `burnin preset import` when the preset is not registered. Do not use Media Pool metadata/color commands for this timeline-specific overlay, and do not expect a clip-level load to affect other occurrences of the same Media Pool source.

## Preflight and readback

Disambiguate the timeline occurrence by track/range/name and record current clip burn-in state in the Data Burn-In Clip tab.

## Public arguments and options

- `CLIP_OR_NAME` (required) — Clip name or burn-in preset name
- `MAYBE_NAME` (optional) — Burn-in preset name when clip is positional
- `--clip` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- With one positional, it is the preset and target comes from `--clip` or current clip; do not reverse them.
- Named clip resolution can be ambiguous when duplicate names exist on the timeline; the command offers no track/time argument.
- The operation is per occurrence.
- Burn-in fields can depend on clip metadata and only appear in viewer/render contexts; always test the actual output path.

## Examples

- `cutagent clip burnin load --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
