# `timeline sync-clips`

Syntax: `cutagent timeline sync-clips [--source VALUE] [--timeline VALUE] [--create-timeline] [--sync VALUE] [--reference VALUE] [--offset VALUE] [--video-track VALUE] [--audio-mode VALUE] [--audio-track VALUE] [--record-frame VALUE] [--plan-only] [--subframe VALUE] [--use-timecode-prior] [--derived-media-dir VALUE] [--max-derived-media-gb VALUE] [--write-multicam-job VALUE] [--write-audio-offsets-json VALUE] [--multicam-name VALUE] [--multicam-timeline-name VALUE] [--multicam-angle VALUE] [--multicam-audio-angle-map VALUE] [--multicam-audio-target VALUE] [--multicam-overlap-angle VALUE] [--multicam-default-video-angle VALUE] [--multicam-default-audio-angle VALUE] [--multicam-sync-anchor VALUE] [--multicam-switch-plan VALUE]`

## Search terms

- sync ordinary timeline clips
- waveform clip synchronization
- manual frame offsets
- place cameras on separate tracks
- subframe audio sync
- derived conform WAV
- generate multicam job JSON
- audio activity offset artifact

## What it does

Place synchronized clips on timeline tracks.

## Do not use when

Use manual mode for known frame offsets.
Do not apply into occupied destination ranges without first inspecting the timeline.

## Preflight and readback

For artifact export, use reviewed non-production paths because existing files are overwritten.
After apply, inspect every returned placement and append result, then verify clip identity, track, start, sync, audio routing, overlap behavior, and fractional/conformed result in DaVinci Resolve. Treat `partial` verification as unresolved and manually remove or repair any partial append. Save only after the real timeline is correct. Review generated JSON before passing it to `multicam create` or `multicam switch`.

## Public arguments and options

- `--source` (optional, repeatable, default: `[]`) — Sync source as LABEL=clip, LABEL=name:clip, LABEL=path:/file.mov, LABEL=media_id:ID, or compound LABEL=path:/file.mov|folder:Bin; repeat for each clip
- `--timeline` (optional) — Target timeline name; defaults to active timeline
- `--create-timeline` (optional, default: `false`) — Create --timeline before placing synced clips
- `--sync` (optional, default: `"waveform"`) — Sync mode: waveform or manual
- `--reference` (optional) — Source label used as waveform reference; defaults to the first --source
- `--offset` (optional, repeatable, default: `[]`) — Manual frame offset as LABEL=FRAMES; repeat when --sync manual
- `--video-track` (optional, repeatable, default: `[]`) — Video track mapping as LABEL=TRACK; defaults to source order V1..VN
- `--audio-mode` (optional, default: `"reference"`) — Audio placement mode: none, reference, or all
- `--audio-track` (optional, repeatable, default: `[]`) — Audio track mapping as LABEL=TRACK; defaults to A1 for reference or source order for all
- `--record-frame/--at` (optional) — Record-domain placement for the earliest synced source; defaults to timeline start
- `--plan-only` (optional, default: `false`) — Resolve clips and offsets but do not append to the timeline
- `--subframe` (optional, default: `"auto"`)
- `--use-timecode-prior` (optional, default: `false`) — Use container/BWF timecode metadata as a waveform search prior; default ignores timecode metadata.
- `--derived-media-dir` (optional) — Directory for conform-derived WAVs; defaults to a .cutagent-derived folder beside the source
- `--max-derived-media-gb` (optional, default: `20.0`) — Cumulative size budget for conform-derived media in this run
- `--write-multicam-job` (optional) — Write a structured multicam job derived from the sync plan
- `--write-audio-offsets-json` (optional) — Write audio-activity offsets JSON derived from the sync plan
- `--multicam-name` (optional)
- `--multicam-timeline-name` (optional) — Target timeline name for the generated multicam job; defaults to the synced timeline
- `--multicam-angle` (optional, repeatable, default: `[]`) — Video source label to use as a multicam angle: LABEL or LABEL=ANGLE; defaults to all video sources
- `--multicam-audio-angle-map` (optional, repeatable, default: `[]`) — Audio source to multicam angle mapping as SOURCE=ANGLE; repeat for each mic source
- `--multicam-audio-target` (optional, repeatable, default: `[]`) — Optional audio target mapping as SOURCE=ANGLE[,ANGLE]
- `--multicam-overlap-angle/--multicam-wide-angle` (optional) — Angle to use for overlap/wide moments in generated audio-activity job
- `--multicam-default-video-angle` (optional) — Default video angle in generated multicam settings
- `--multicam-default-audio-angle` (optional) — Default audio angle in generated multicam settings
- `--multicam-sync-anchor` (optional) — Program sync anchor as a generated multicam angle or sync source label
- `--multicam-switch-plan` (optional) — Path to include in the generated multicam switch --write-plan command

## Boundaries and gotchas

- At least two `--source` values are required.
- Each source must resolve uniquely in the current project's Media Pool.
- `--reference` must name one of the supplied sources.
- Repeated offset or track-map entries for the same label use the last value rather than reporting a duplicate.
- `--use-timecode-prior` makes metadata a waveform search prior, not the final authority.
- `--timeline NAME` switches the active timeline during a real apply and does not restore the former timeline.
- `--create-timeline` requires `--timeline`, rejects an existing same-name timeline, and creates/switches before source planning completes.
- Critically, that non-applying plan is still calculated from the currently active timeline's FPS, start frame, and timeline state; it does not switch to or instantiate the named target.
- `--record-frame`/`--at` anchors the earliest normalized source and defaults to timeline start.
- Explicit track indexes must be positive.
- Audio mode defaults to `reference`, placing audio only for the reference source on A1.
- `--audio-mode all` places every source's audio on successive audio tracks; `none` omits audio placements.
- In manual mode, sources are not probed for audio-only classification; an audio-only file can consequently receive a planned video placement.
- Required destination tracks are added before appends; added tracks are not rolled back.
- `conform` is meaningful for audio-only files; non-audio-only sources fall back to fractional when supported and needed, otherwise round.
- `--max-derived-media-gb` defaults to 20, has no CLI lower-bound validation, and a nonpositive value effectively refuses positive-size conform output.
- Drift conform is applied only when measured drift across the span reaches roughly half a timeline frame.
- Verification does not compare the found item's media identity or name; a pre-existing item at the expected start can satisfy it.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline sync-clips --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
