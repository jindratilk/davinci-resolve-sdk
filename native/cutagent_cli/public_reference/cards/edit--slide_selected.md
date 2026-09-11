# `edit slide-selected`

Syntax: `cutagent edit slide-selected [--clip VALUE] [--at VALUE] [--direction VALUE] [--steps VALUE]`

## Search terms

- slide clip left or right
- move shot while adjusting neighboring edit points
- slide selected timeline item one frame
- shift clip without changing source in out
- move middle clip and reflow neighbors
- nudge clip position in Slide mode
- change both surrounding cut points
- slide edit by several frames
- reposition clip between adjacent clips
- preserve clip content while moving record span
- move shot earlier and extend right neighbor

## What it does

Slide the selected clip in DaVinci Resolve.

## Do not use when

Use `edit slip-selected` when the target must stay at the same record span while its source content changes. Use trim/roll commands when only an edit boundary should move, or ordinary position/append operations when the whole clip should move without consuming/extending adjacent media.
Do not use this on the first/last clip, across gaps/overlaps, or without immediate neighbors on the same track. Do not run when DaVinci Resolve page readback is null or UI/menu language differs from English.

## Preflight and readback

Checkpoint the timeline and calculate the expected target/neighbor frame changes.
Afterward, inspect the linked target and both neighbors by stable identity and exact frames/source ranges. Verify the target moved by exactly the requested signed steps without source change, the left/right edits reflowed without gaps/overlaps, audio/link sync is intact and no stacked clip was accidentally selected. Page/playhead restoration is reported.

## Public arguments and options

- `--clip` (optional) — Target video clip name; defaults to current clip
- `--at` (optional) — Record-domain frame/timecode inside the target video clip
- `--direction` (optional, default: `"right"`)
- `--steps` (optional, default: `1`)

## Boundaries and gotchas

- Only macOS is supported.
- `--steps` is constrained to 1–100.
- Before mutation, every selected linked track must have exact left/right adjacency and enough neighbor/source-handle capacity for all steps.
- `--at` does not disambiguate duplicate named targets, though it is subsequently required to fall inside the chosen target.
- Without `--at`, selection uses an interior frame; a one-frame clip uses its start frame.
- Adjacency is exact: left.end must equal target.start and right.start must equal target.end.
- One AppleScript menu invocation is made per frame, with only 50 ms between nudges and 150 ms before readback.
- Exact target record movement, unchanged target source range, adjacent duration/source-handle reflow, linked A/V state, and protected A/V state are checked.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent edit slide-selected --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
