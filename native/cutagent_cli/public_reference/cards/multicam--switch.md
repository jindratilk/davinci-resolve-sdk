# `multicam switch`

Syntax: `cutagent multicam switch --multicam-name VALUE [--job VALUE] [--job-json VALUE] [--angle VALUE] [--timeline-name VALUE] [--switch-by VALUE] [--transcript VALUE] [--speaker-map VALUE] [--audio-source VALUE] [--audio-angle-map VALUE] [--audio-target VALUE] [--audio-sync VALUE] [--sync-reference-audio VALUE] [--sync-reference-angle VALUE] [--audio-offsets-json VALUE] [--overlap-policy VALUE] [--overlap-angle VALUE] [--analysis-window-ms VALUE] [--activity-floor-db VALUE] [--activity-margin-db VALUE] [--dominance-margin-db VALUE] [--min-switch-ms VALUE] [--switch-delay-ms VALUE] [--max-silence-hold-ms VALUE] [--video-source-offset VALUE] [--video-only] [--audio-only] [--plan-only] [--write-plan VALUE] [--replace-active-timeline]`

## Search terms

- transcript multicam editing
- audio activity multicam switching
- multicam segment rewrite
- video-only multicam switch
- audio-only multicam switch
- replace active timeline
- create switched timeline

## What it does

Apply a saved multicam switch plan.

## Do not use when

Do not combine structured `--job`/`--job-json` with convenience planning flags, except that the separately required `--multicam-name` is allowed with a structured job.
Do not use both `--video-only` and `--audio-only`. The default linked scope rewrites both.
Do not mistake `--replace-active-timeline` for a narrow patch. It clears existing items in the selected scope before appending/materializing the multicam segments.
Do not expect `--new-timeline` to reuse an existing timeline.

## Preflight and readback

Generate `--plan-only` first. Review every segment's angle, clip, source frames, record frames, duration, ordering, overlap/silence decisions, unresolved segments, and support tier.
For a new timeline, verify the requested name is unused.
Then verify the same timeline in DaVinci Resolve, switch-menu behavior, audio/video sync, every boundary, playback, and representative renders.

## Public arguments and options

- `--multicam-name` (required)
- `--job` (optional) — Path to a structured multicam job JSON file
- `--job-json` (optional) — Inline structured multicam job JSON
- `--angle` (optional, repeatable) — Repeatable source spec; repeat a label for separate sequential clips on one angle: A=camA.mov
- `--timeline-name/--timeline` (optional) — Optional target timeline name
- `--switch-by` (optional) — Convenience switch planner: transcript or audio-activity
- `--transcript` (optional) — Path to ElevenLabs Scribe v2 JSON transcript for convenience switch planning
- `--speaker-map` (optional) — Optional explicit speaker mapping: speaker_0=A,speaker_1=B
- `--audio-source` (optional, repeatable) — Repeatable audio activity source spec: id=/path/audio.wav
- `--audio-angle-map` (optional) — Audio activity mapping: source_id=ANGLE,source_id=ANGLE
- `--audio-target` (optional, repeatable) — Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B
- `--audio-sync` (optional) — Audio sync mode for audio-activity: prealigned, waveform, offsets-json
- `--sync-reference-audio` (optional) — Reference camera/audio file for waveform audio sync
- `--sync-reference-angle` (optional) — Reference angle for waveform audio sync when the angle has a source path
- `--audio-offsets-json` (optional) — Path to JSON offsets object for audio-activity sync
- `--overlap-policy` (optional) — Overlap handling: angle/wide, dominant, hold, mark
- `--overlap-angle/--wide-angle` (optional) — Multicam angle to use for overlap/wide moments
- `--analysis-window-ms` (optional) — Audio activity analysis window in milliseconds
- `--activity-floor-db` (optional) — Absolute dBFS floor required for activity
- `--activity-margin-db` (optional) — dB above per-source noise floor required for activity
- `--dominance-margin-db` (optional) — Leader margin in dB required before avoiding overlap handling
- `--min-switch-ms` (optional) — Minimum planned video switch duration in milliseconds
- `--switch-delay-ms` (optional) — New audio target must persist this long before switching
- `--max-silence-hold-ms` (optional) — Hold previous angle through silence up to this duration
- `--video-source-offset` (optional, repeatable) — Per-angle source-frame offset for rendered video: A=104
- `--video-only` (optional, default: `false`) — Apply multicam angle switches to timeline video only and preserve timeline audio
- `--audio-only` (optional, default: `false`) — Apply multicam angle switches to timeline audio only and leave timeline video untouched
- `--plan-only` (optional, default: `false`) — Build and return the multicam switch plan without connecting to DaVinci Resolve or applying it
- `--write-plan` (optional) — Optional JSON path to write the generated switch plan
- `--replace-active-timeline/--new-timeline` (optional, default: `true`) — Rewrite the current active timeline or create/target another one from the job plan

## Boundaries and gotchas

- `--multicam-name` is always required, including structured jobs and plan-only.
- Structured input requires exactly one of `--job` or `--job-json`.
- Convenience input requires at least one `--angle` and `--timeline-name`.
- Convenience switch mode defaults to `transcript` and then requires `--transcript`.
- Convenience audio activity requires `--audio-sync` and at least one `--audio-source`.
- `--plan-only` is nonmutating even without global `--dry-run`.
- Plan-only sets audio-activity unresolved targets allowed.
- Ordinary global dry-run also uses the synthetic context and returns only a summary, not the full plan.
- `--replace-active-timeline` is the default; `--new-timeline` flips it false.
- Video-only documentation says timeline multicam audio is removed, but scope cleanup targets video only; verify actual audio outcome in DaVinci Resolve.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam switch --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
