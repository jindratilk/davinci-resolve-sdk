# `fairlight bounce track`

Syntax: `cutagent fairlight bounce track [--track VALUE] [--destination-track VALUE] [--record-frame VALUE] [--output VALUE] [--format VALUE] [--codec VALUE] [--bitdepth VALUE] [--samplerate VALUE] [--clip-name VALUE]`

## Search terms

- bounce one Fairlight track
- print audio track effects
- render a single audio track
- commit track processing to audio
- bounce track to another track
- make a stem from one timeline track
- flatten one Fairlight channel
- render and reimport an audio track
- isolate track and print it
- create audio clip from track mix
- bounce dialogue track
- print one track through Main mix

## What it does

Bounce a Fairlight audio track to another audio track.

## Do not use when

Use `fairlight bounce mix-to-track` when all enabled audio tracks reaching Main should be printed together. Use `fairlight export audio` when only an external file is wanted and no Media Pool import/timeline append is desired.
Do not use this as a raw source extraction, pre-fader/direct-out export or independent bus stem. Disabling other timeline audio tracks does not bypass processing on the selected track or Main path.
Do not use it merely to freeze one clip's effect when the rest of its track must remain active or when only a clip range is wanted: this command renders the full timeline duration and isolates the entire audio track. A clip-level render/replace or explicit range export is the correct boundary.
Do not run while an active render or valuable queued jobs exist. Do not use it when temporarily changing enabled states is unsafe, for example during playback/recording or concurrent editing.

## Preflight and readback

Before running, make the exact timeline active and list every audio track with index, name, enabled state, lock state and item range. Confirm the requested track is the intended source and record the destination track's item count/occupied ranges. Check whether the source was originally disabled—the command will enable and render it. Preserve every render-queue job and ensure no render is active.
Remember that render length follows the whole timeline, including frames contributed only by disabled tracks. Prefer an omitted placement or a relative frame reference such as `144f` until the timecode double-offset bug is fixed.
Verify the exact appended item, destination count, source path and playhead, then clean the completed render job if appropriate.

## Public arguments and options

- `--track/-t` (optional) — Audio track index to bounce
- `--destination-track/--to-track` (optional) — Existing audio track for the bounced render; omitted creates a new stereo audio track
- `--record-frame/--at` (optional) — Record-domain placement frame/timecode; omitted uses the timeline start frame
- `--output/--output-path` (optional) — Rendered bounce media path; omitted uses the CutAgent exports folder
- `--format` (optional, default: `"MP4"`) — Render format
- `--codec` (optional, default: `"H.264"`) — Render codec
- `--bitdepth` (optional, default: `16`) — Audio bit depth
- `--samplerate` (optional, default: `48000`) — Audio sample rate
- `--clip-name` (optional) — Name to assign to the appended bounced timeline item when DaVinci Resolve allows it

## Boundaries and gotchas

- Isolation affects audio tracks only.
- The command does not prevent overlap or recursive future bounces.
- The completed job remains in the queue after success and must be removed separately.
- Dry-run does not inspect track enabled states, timeline duration/content, render queue, format/codec support, output path, destination, record frame or placement collisions.
- Omitting `--destination-track` always adds a new stereo track; it does not search for an empty compatible track.
- Omitting `--record-frame` uses the timeline start.
- `--clip-name` is best-effort and setter failures are ignored.
- It does not compare audio, prove source isolation, detect clipping/silence or verify signal routing.
- The command does not restore playhead or selection.

## DaVinci Resolve editions

DaVinci Resolve Free/other OS render formats and audio codecs can differ.

## Examples

- `cutagent fairlight bounce track --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
