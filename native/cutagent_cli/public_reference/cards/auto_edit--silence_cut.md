# `auto-edit silence-cut`

Syntax: `cutagent auto-edit silence-cut [--threshold-db VALUE] [--auto-threshold] [--min-silence VALUE] [--padding VALUE] [--name VALUE] [--wav-path VALUE]`

## Search terms

- remove silence from timeline
- cut out long pauses
- make jump cuts where nobody talks
- close gaps between spoken sections
- delete quiet sections of an edit
- trim dead air automatically
- silence removal timeline copy
- condense interview by audio level
- remove pauses but keep breathing room
- rebuild timeline without silent ranges

## What it does

Create a new timeline with silent segments removed.

## Do not use when

Use `audio duck` when speech should lower background music without deleting time. Use `edit ripple-delete`, blade/delete commands, or explicit range editing when the cut locations are known or visual content rather than audio level determines the edit. Use transcript/subtitle workflows when words, speakers, or semantic pauses define what should be removed; this command sees amplitude only. Do not use it to destructively shorten the current timeline: it deliberately makes a separate timeline.

## Preflight and readback

Confirm the intended active timeline, timeline fps/start timecode, track layout, source item availability, and that the audible mix represents the material to judge. Inspect or render representative audio first to choose a threshold and minimum duration; quiet speech below the threshold is indistinguishable from unwanted silence. Supply a unique output name and a writable, unique `--wav-path`. Listen across each join and inspect video continuity; item-count verification cannot judge edit taste, clicks, lost quiet speech, effects, transitions, keyframes, or grades.

## Public arguments and options

- `--threshold-db` (optional, default: `-40.0`) — Silence threshold in dB
- `--auto-threshold/--fixed-threshold` (optional, default: `false`) — Calibrate the silence threshold from rendered timeline dynamics
- `--min-silence` (optional, default: `0.5`) — Minimum silence duration in seconds
- `--padding` (optional, default: `0.1`) — Keep this much time around speech in seconds
- `--name` (optional) — Name for the new timeline
- `--wav-path` (optional) — Temporary WAV render path

## Boundaries and gotchas

- The returned command result does not expose the actual analysis path.
- Timeline-item-only state such as transitions, Fusion compositions, keyframes, per-item grades, speed changes, retimes, clip flags/colors, linked relationships, and some audio processing are not explicitly copied by this routine.
- `--padding` shrinks the portion removed: padding is added to a silence start and subtracted from its end, except at timeline boundaries.
- A trailing gap only counts if DaVinci Resolve reports it inside timeline duration; empty space after the last item is normally outside the timeline.
- Reusing one path overwrites/changes the prior render output; clean it separately when it is only temporary.

## Examples

- `cutagent auto-edit silence-cut --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
