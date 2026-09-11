# `color secondary subject-isolation`

Syntax: `cutagent color secondary subject-isolation [--clip VALUE] [--pattern-center VALUE] [--comp VALUE]`

## Search terms

- isolate a person for grading
- create subject ellipse mask
- track subject with power window
- make tracked oval around face
- build subject secondary grade
- add ellipse and tracker in Fusion
- follow a person with grading mask
- create portrait isolation setup
- track an elliptical color correction
- set up subject spotlight grade
- make face window tracker
- isolate central subject in Fusion

## What it does

Create a subject-isolation stack using ellipse window plus tracker.

## Do not use when

Do not use when “subject isolation” means Magic Mask/person segmentation, automatic face/body detection or a finished tracked power window; this wrapper provides none of those. Use `color secondary tracked-window` when the request explicitly names a rectangle/ellipse tracked-window scaffold, or dedicated window commands when geometry/softness must be set. Use `color primary set` to define the actual correction.

## Preflight and readback

Before creation, choose the correct reference frame and inspect where the subject lies; `--pattern-center` is normalized Fusion coordinate input but not range-limited. Inspect/export the comp and note all current mask-chain tools and primaries. Confirm that a fixed centered 50%-size, hard-edged ellipse is an acceptable starting shape and that you will manually size/position/link/track it afterward. Use dry-run for syntax only.
Render frames at start/middle/end to prove the subject remains isolated. Apply the desired primary adjustment only after the matte works. Check pre-existing windows/trackers because the wrapper may reorder them and is not transactionally isolated.

## Public arguments and options

- `--clip` (optional) — Clip name (current clip when omitted)
- `--pattern-center` (optional, default: `"0.5,0.5"`) — Tracker pattern center X,Y
- `--comp` (optional, default: `1`) — Fusion composition index

## Boundaries and gotchas

- There is no subject detection of any kind. “Subject” is only the name of a fixed recipe: default ellipse plus Tracker.
- The option changes the Tracker pattern only; it does not move the visible window over the chosen subject.
- Pattern center validation checks exactly two finite numbers but does not constrain them to 0..1.
- The final success verification checks only that newly named ellipse/tracker are active and graph invariants pass.
- It does not verify subject coverage, ellipse geometry, tracker center/path, links or pixels.
- Dry-run is safe/non-mutating and does not connect.
- The command does not remove them if a later recipe stage fails.

## Examples

- `cutagent color secondary subject-isolation --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
