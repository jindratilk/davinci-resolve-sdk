# `edit slip-selected`

Syntax: `cutagent edit slip-selected [--clip VALUE] [--at VALUE] [--direction VALUE] [--steps VALUE]`

## Search terms

- slip clip source content
- change source in out without moving clip
- nudge footage inside timeline item
- slip selected video one frame
- keep edit points but show earlier frames
- shift clip content left or right
- adjust shot timing inside fixed duration
- replace frames while preserving record span
- slip clip by several frames
- use source handles without moving neighbors
- change in and out together

## What it does

Slip the selected clip in DaVinci Resolve.

## Do not use when

Use `edit slide-selected` when the clip's source content must remain fixed while its record position moves and adjacent cuts reflow. Use trim/roll commands to change only one edge, retime commands to change playback speed, or audio/subframe GUI workflows for audio-only slips.
Do not use when the source has insufficient head/tail handles for every requested step, when the target is ambiguous across tracks, on Windows, or when DaVinci Resolve page readback/English menu automation is unreliable. The command follows and verifies the target's stable linked A/V group.

## Preflight and readback

Before mutation, inspect exact target record and source start/end plus left/right source handles, calculate the expected signed source delta, and checkpoint the timeline. Confirm a unique video target, an `--at` strictly inside it, macOS Accessibility, English DaVinci Resolve menus, no modal, and reliable Edit-page readback.
Afterward, inspect the complete linked-group and protected-timeline readback: record span and duration must be unchanged; source start/end must both shift by the exact expected amount; neighbors and total timeline duration must remain unchanged. Page/playhead restoration is reported. Play/render the shot boundaries when content-level continuity matters.

## Public arguments and options

- `--clip` (optional) — Target video clip name; defaults to current clip
- `--at` (optional) — Record-domain frame/timecode inside the target video clip
- `--direction` (optional, default: `"right"`)
- `--steps` (optional, default: `1`)

## Boundaries and gotchas

- Selection is video-led; there is no audio-only, Slip Audio or subframe path.
- No adjacent clips are required (unlike Slide), but sufficient unused source frames on both ends are preflighted for every requested nudge.
- `--at` does not disambiguate duplicate named targets, though it must subsequently fall inside the chosen target.
- Without `--at`, the route uses an interior frame; a one-frame target uses its start frame.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent edit slip-selected --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
