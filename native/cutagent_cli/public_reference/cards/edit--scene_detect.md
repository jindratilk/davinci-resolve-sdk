# `edit scene-detect`

Syntax: `cutagent edit scene-detect`

## Search terms

- detect scene cuts on timeline
- automatically split shots
- find hard cuts in flattened video
- cut long clip at scene changes
- detect edits in rendered master
- split timeline by visual transitions
- add edits at shot boundaries
- scene cut analysis in DaVinci Resolve
- break video into detected scenes
- find cuts in compilation clip
- auto blade on scene changes

## What it does

Run DaVinci Resolve scene detection on the current timeline.

## Do not use when

Use `edit blade` when exact cut frames are already known, especially from transcript/timecode analysis. Use Media page/UI scene-cut detection when the target is a source media file rather than the already assembled active timeline. Use silence/transcript workflows for audio or dialogue boundaries; this command has no audio-content detector.
Do not use this when only one named clip, track or marked range may be touched—the command exposes no target selector. Do not run on a carefully graded/effected flattened timeline without a checkpoint and post-split state review.

## Preflight and readback

Before mutation, confirm the exact active timeline, inventory every video track/item and checkpoint/duplicate it. Identify which long/flattened clips are expected to contain detectable visual cuts and review transitions, retimes, Fusion/OFX, grades, links and locks.
Afterward, independently list all video/audio tracks, identify every new boundary and compare it frame-accurately with the source image. Confirm record/source continuity, linked audio behavior and preservation of grades/effects/retimes/markers across split halves. Render representative boundaries.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There are no threshold, sensitivity, minimum-shot-length, track, clip, range or marker options.
- “Current timeline” is the only scope.
- The command does not inspect or require a UI-selected clip despite one diagnostic possible-cause string mentioning selected-clip eligibility.
- Dry-run exits before connecting and returns only a generic message.
- Verification waits only while total video item count is unchanged, polling every 100 ms for about three seconds.
- It cannot say which track/item was split or whether the cut appeared at a real scene boundary.
- Audio item counts are collected and reported but do not participate in success.
- The command does not verify source continuity, item names, durations, linked A/V, track locks, effects, grades, Fusion graphs, transitions or rendered pixels after splitting.
- Newly created edit points can change clip-local ownership of keyframes, effects, markers or grades according to DaVinci Resolve behavior; CutAgent does not inspect that propagation.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent edit scene-detect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
