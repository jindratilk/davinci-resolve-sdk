# `fairlight bounce mix-to-track`

Syntax: `cutagent fairlight bounce mix-to-track [--bus VALUE] [--destination-track VALUE] [--record-frame VALUE] [--output VALUE] [--format VALUE] [--codec VALUE] [--bitdepth VALUE] [--samplerate VALUE] [--clip-name VALUE]`

## Search terms

- bounce Fairlight mix to track
- print the main mix
- render mix and put it on timeline
- bounce Main bus to audio track
- flatten audio mix into one clip
- create a stereo mixdown track
- print master audio back into timeline
- render and reimport timeline audio
- make a mixed audio stem
- commit the full Fairlight mix
- bounce bus to track
- create an audio-only mixdown clip

## What it does

Bounce the main Fairlight mix to an audio track.

## Do not use when

Use `fairlight bounce track` when only one audio track should be printed; that command temporarily isolates a source track. This command renders every enabled contribution reaching the Main mix. Use `fairlight export audio` when a file export is wanted without importing/appending it back into the timeline.
Do not use this for a specific non-Main bus, FlexBus or stem.
Do not run another mix bounce while a prior bounced mix is enabled on the timeline unless the user intentionally wants that printed again.

## Preflight and readback

Before running, capture the active project/timeline, full audio track map, enabled/locked state, current playhead, Main output gain and timeline start/end. Ensure there is no active render and preserve or finish every queued render job. Inspect the target track for collisions and verify it exists; when omitting the destination, confirm that adding a new stereo track is desired.
Use a fresh output path whose parent is writable. Confirm the requested bit depth/sample rate with a short test render. Prefer an omitted placement (timeline start) or a relative frame reference such as `72f`; do not trust a timeline-started timecode until the double-offset behavior described below is fixed.
Verify the Media Pool import and map the destination track before/after: exact item start/end, source path, name and track count. Recheck the playhead and restore it if needed. Audition/render the appended clip against the original mix, check for doubled audio, and inspect the render queue. Remove the completed job, unwanted imported asset/file or temporary track explicitly; the command does not clean them up.

## Public arguments and options

- `--bus` (optional) — Bus/main output to bounce
- `--destination-track/--to-track` (optional) — Existing audio track for the bounced render; omitted creates a new stereo audio track
- `--record-frame/--at` (optional) — Record-domain placement frame/timecode; omitted uses the timeline start frame
- `--output/--output-path` (optional) — Rendered bounce media path; omitted uses the CutAgent exports folder
- `--format` (optional, default: `"MP4"`) — Render format
- `--codec` (optional, default: `"H.264"`) — Render codec
- `--bitdepth` (optional, default: `16`) — Audio bit depth
- `--samplerate` (optional, default: `48000`) — Audio sample rate
- `--clip-name` (optional) — Name to assign to the appended bounced timeline item when DaVinci Resolve allows it

## Boundaries and gotchas

- There is no in/out or custom-range option.
- Deliver format, codec, mode and settings are restored only best-effort.
- The requested video-codec label is used only to satisfy the Deliver format/codec selector.
- Dry-run does not validate format/codec availability, output writability, bit depth/sample rate, record-frame parsing, destination track existence, timeline content or rendering.
- Placement happens only after the full render.
- Omitting `--destination-track` creates a new stereo track after the current last audio track.
- It does not reuse an empty track.
- Omitting `--record-frame` uses the timeline start correctly.
- `--clip-name` is best-effort.
- Verification proves only that the append returned items, the destination item count increased, and—when readable—the returned item start matched the resolved frame.
- It does not compare waveforms, confirm Main-bus routing, detect silence/clipping or prove the audible mix.

## DaVinci Resolve editions

Format/codec availability and rendering behavior can differ in DaVinci Resolve Free and across operating systems.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight bounce mix-to-track --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
