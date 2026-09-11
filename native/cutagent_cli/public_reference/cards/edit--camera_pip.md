# `edit camera-pip`

Syntax: `cutagent edit camera-pip CAMERA_CLIP [--background VALUE] [--at VALUE] [--duration VALUE] [--camera-track VALUE] [--background-track VALUE] [--zoom VALUE] [--pan VALUE] [--tilt VALUE] [--anchor VALUE] [--margin VALUE] [--verify-placement] [--verify-rendered-placement] [--verify-frame VALUE] [--verify-output-dir VALUE] [--render-tolerance VALUE] [--render-iterations VALUE] [--render-diff-threshold VALUE] [--corner-radius VALUE] [--softness VALUE] [--opacity VALUE] [--apply-existing]`

## Search terms

- make camera picture in picture
- put webcam over screen recording
- add talking head overlay
- place presenter in corner
- shrink camera clip to top right
- create rounded webcam bubble
- overlay camera on background video
- apply PiP to existing timeline clip
- position video inset by anchor
- make facecam overlay
- add camera box without ffmpeg
- move clip to bottom left corner

## What it does

Create a picture-in-picture camera layout.

## Do not use when

Use a normal clip transform/position command when one known item only needs zoom or coordinates and no PiP workflow, track creation, append, rename or Fusion mask. Use overlay/title/image commands for a still logo, lower third or generated graphic rather than a camera video. Use Fusion composition commands when the desired shape, border, shadow, crop or animation is more complex than one static rectangle mask.
Do not use append mode when the camera item is already in the timeline; use `--apply-existing` after narrowing the name and track. Conversely, do not use `--apply-existing` to place new Media Pool media or to establish a synchronized background—it ignores `--background`, `--at` and `--duration`. Do not treat `--verify-placement` as visual verification; use `--verify-rendered-placement` or an independent frame export when pixel position matters.

## Preflight and readback

Before append mode, confirm the active timeline, resolution/FPS, destination track locks, Media Pool clip names, source lengths and intended record position. List existing items on both requested tracks and dry-run the exact command. If appending both camera and background, verify that their source ranges and durations align. Before `--apply-existing`, list the camera track and ensure the search string cannot match another item; use an exact distinctive filename, not a short common substring.
Afterward, list both tracks and confirm the expected item names, start/end frames, stacking order and absence of accidental duplicates. Inspect the camera timeline item's transform and Fusion graph, then export a representative frame to verify the visible inset, crop, opacity and background. If verification reports failure or the command errors, re-list tracks and Fusion tools anyway: this workflow is not transactional and earlier mutations can remain.

## Public arguments and options

- `CAMERA_CLIP` (required) — Camera clip to place as picture-in-picture
- `--background` (optional) — Optional background/screen clip to append on track 1
- `--at` (optional) — Record-domain start position
- `--duration` (optional) — Optional source duration for appended clips
- `--camera-track/--track` (optional, default: `2`) — Video track for the PiP camera clip
- `--background-track` (optional, default: `1`) — Video track for the optional background clip
- `--zoom` (optional, default: `0.32`)
- `--pan/--position-x` (optional, default: `0.62`) — PiP horizontal position
- `--tilt/--position-y` (optional, default: `-0.56`) — PiP vertical position
- `--anchor` (optional) — Compute PiP Pan/Tilt from an anchor: top-left|top-right|bottom-left|bottom-right|center
- `--margin` (optional) — Anchor edge margin in timeline pixels; default scales from 24 px at 1920x1080
- `--verify-placement` (optional, default: `false`) — Read back applied transform properties and include placement verification notes
- `--verify-rendered-placement` (optional, default: `false`) — Temporarily disable/restore the camera track, export background/foreground frames, measure the rendered PiP bbox, and tune Pan/Tilt
- `--verify-frame` (optional) — Timeline position for rendered placement verification; default samples the camera item midpoint
- `--verify-output-dir` (optional) — Directory for rendered placement verification frames
- `--render-tolerance` (optional, default: `4.0`) — Rendered placement tolerance in pixels
- `--render-iterations` (optional, default: `3`)
- `--render-diff-threshold` (optional, default: `8`) — RGB diff threshold for detecting the PiP overlay against background
- `--corner-radius` (optional, default: `0.12`) — Fusion RectangleMask CornerRadius; 0 disables rounded crop
- `--softness` (optional, default: `0.002`) — Fusion RectangleMask SoftEdge
- `--opacity` (optional, default: `100.0`) — PiP opacity; no border is added by this command
- `--apply-existing` (optional, default: `false`) — Apply PiP transform to existing items on the camera track instead of appending new clips.

## Boundaries and gotchas

- It behaves as a zero-based source-out frame for this command, not as a duration added to an arbitrary source start.
- Dry-run returns before connecting.
- It does not resolve the Media Pool clips, ensure tracks, validate source bounds/record placement, compute anchor geometry, inspect an existing match, exercise Fusion or predict append success.
- It does not inspect source aspect ratio, input scaling, crop, rotation, blanking, stabilization or existing Fusion output; the estimated box can differ from rendered pixels.
- An explicit `--margin` is in timeline pixels and requires `--anchor`.
- `--verify-rendered-placement` also requires `--anchor`.
- Ordinary `--verify-placement` is property readback only.
- `--apply-existing` uses case-insensitive substring matching against the supplied camera clip string, its basename and stem.
- Set it to zero when an existing Fusion composition must not be touched.
- Re-running the command, including `--apply-existing`, can accumulate masks rather than updating an earlier CutAgent mask.
- An omitted background does not create one; lower tracks show through.
- The command does not synchronize audio, mute camera audio, link camera/background items or resolve multicam angles.
- Appending an audiovisual camera asset may therefore add behavior beyond the visible inset that must be checked separately.

## DaVinci Resolve editions

Appending an audiovisual camera asset may therefore add behavior beyond the visible inset that must be checked separately. - DaVinci Resolve Free/Studio differences are not explicitly gated here.

## Stable public error codes

- `API_CALL_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent edit camera-pip --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
