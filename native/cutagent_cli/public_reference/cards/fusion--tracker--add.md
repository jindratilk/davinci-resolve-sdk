# `fusion tracker add`

Syntax: `cutagent fusion tracker add [--pattern-center VALUE]`

## Search terms

- add Fusion tracker
- create point tracker Fusion
- add IntelliTrack node
- Tracker PatternCenter ignored
- PatternCenter1 Fusion
- tracker initial position
- Fusion tracking setup
- tracker dry-run safe
- embedded tracker partial mutation
- tracker center readback
- track motion in Fusion
- Tracker1 PatternX PatternY

## What it does

Add a Fusion tracker.

## Do not use when

Do not use this command when the requested initial pattern center must be honored.
Do not use this command as if it performs tracking.
Do not run against an ambiguous composition. There is no project, timeline, clip, track, record-frame, composition-index, branch, tracker-index, or time selector.
Do not use for planar tracking, camera tracking, surface tracking, person tracking, Magic Mask, stabilization, match move setup, corner positioning, or compositing mode without the appropriate specialized workflow.

## Preflight and readback

Before execution, inspect `status`, `fusion comp current`, and `fusion tool list`; export the graph and a representative frame.
Use dry-run to validate exact `x,y` syntax. Invalid single-value center fails before DaVinci Resolve is touched.
Treat null generic readback plus unchanged indexed center as proof the requested location was ignored.
Verify topology.
Export the same frame and compare with baseline.
Before actual tracking, explicitly configure PatternCenter1, pattern/search sizes, tracker type/channel, reference time, and operation mode, then run the intended tracking direction and verify TrackedCenter/path data across frames.
After testing, delete Tracker nodes in reverse order and export the graph.

## Public arguments and options

- `--pattern-center/-p` (optional, default: `"0.5,0.5"`) — Initial pattern center X,Y

## Boundaries and gotchas

- `--pattern-center` must use exactly `x,y`.
- Adding the tool does not execute tracking, produce a path, configure match move, or verify foreground/background connections.

## DaVinci Resolve editions

Studio external inserted the new Tracker inline as `MediaIn1 -> Tracker1 -> MediaOut1`.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fusion tracker add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
