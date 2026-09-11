# `fairlight audio-pan batch`

Syntax: `cutagent fairlight audio-pan batch --value VALUE [--timeline VALUE] [--item-id VALUE] [--track-index VALUE] [--start-frame VALUE] [--end-frame VALUE] [--record-frame VALUE] [--record-duration VALUE] [--record-end VALUE] [--input VALUE] [--allow-empty] [--allow-multiple]`

## Search terms

- batch pan audio clips
- bulk audio pan
- pan several timeline clips
- set clip pan for a time range
- move multiple clips off center
- center many audio clips
- set pan by audio item ID
- change left right balance on selected clips
- apply one pan value to multiple audio items
- pan every clip overlapping a range
- archive-backed clip pan
- batch Fairlight clip panning

## What it does

Apply one audio pan to many audio items.

## Do not use when

Do not use this for a Fairlight mixer channel, bus, track pan control or pan automation curve. Use the applicable track/bus mixer command for channel-level panning, or Fairlight automation commands when the pan must change during playback.
Do not choose a broad range merely because it is convenient when the user identified exact clips. Resolve item IDs and submit those.

## Preflight and readback

Confirm the target audio format and monitoring layout if the user's requested direction matters. Make a separate project checkpoint and decide explicitly whether each range is allowed to match more than one item.
After mutation, require the intended project and timeline—not `Untitled Project`—to reopen. Re-run a timeline item map to prove positions and durations did not change, then audition or render through the intended channel layout. If the command switched timelines, restore the editor's previous timeline when the workflow is complete.

## Public arguments and options

- `--value` (required) — Audio pan value from -100 to 100
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--item-id` (optional, repeatable)
- `--track-index` (optional) — Audio track index for time selectors
- `--start-frame` (optional) — Record-domain range start
- `--end-frame` (optional) — Record-domain range end
- `--record-frame` (optional) — Record-domain point or range start
- `--record-duration` (optional) — Duration from --record-frame
- `--record-end` (optional) — Record-domain range end from --record-frame
- `--input/--batch` (optional) — JSON batch file path
- `--allow-empty` (optional, default: `false`) — Do not fail when selectors match no items
- `--allow-multiple` (optional, default: `false`) — Allow one selector to update multiple items

## Boundaries and gotchas

- `--value` must be finite and lies in the inclusive range -100 through 100.
- Do not promise that a sign means a particular audible side without verifying the target clip format and DaVinci Resolve panner behavior.
- JSON entries cannot carry independent pan values.
- An item-ID selector cannot be mixed with track/time fields in the same entry.
- Durations must resolve to more than zero frames and ends must be after starts.
- At a cut, the item beginning on that frame matches; the item ending there does not.
- Range matching uses overlap rather than containment.
- Without `--allow-multiple`, a single selector that matches two items aborts the entire batch.
- Several separate selectors that each match one item do not require the flag.
- `--allow-empty` changes a missing match from an error into a zero-target selector result.
- It does not inspect untargeted rows, the Fairlight UI, the monitoring layout or rendered audio.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight audio-pan batch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
