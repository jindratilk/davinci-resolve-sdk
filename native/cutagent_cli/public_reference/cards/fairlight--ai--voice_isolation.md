# `fairlight ai voice-isolation`

Syntax: `cutagent fairlight ai voice-isolation AMOUNT [--clip VALUE]`

## Search terms

- isolate a voice from background noise
- remove ambience behind speech
- clean noisy dialogue with Voice Isolation
- make a speaker clearer
- suppress room noise on one clip
- set Voice Isolation strength
- turn on Voice Isolation for a clip
- AI voice cleanup
- separate speech from background audio
- reduce crowd noise behind an interview
- set clip Voice Isolation amount
- apply DaVinci Resolve Voice Isolation

## What it does

Set AI Voice Isolation amount (0-100).

## Do not use when

Use `clip voice-isolation --disable` when Voice Isolation must be turned off: this command always sends `isEnabled:true` and has no disable option. Use `clip voice-isolation` when the requested operation must preserve/alter enable state separately from amount.
Use `timeline voice-isolation get/set` or `fairlight voice-isolation get/set` for a track/timeline Voice Isolation state; those commands target a track index rather than a TimelineItem. Use `fairlight ai dialogue-leveler` for lifting soft dialogue or its Dialogue Leveler cleaner/output-gain controls.

## Preflight and readback

Before mutation, verify the active project/timeline and identify a uniquely named target. Prefer an explicit name over omission, and confirm the name is not duplicated across video/audio tracks. A dry-run is useful for range/rounding review but is not target preflight.

## Public arguments and options

- `AMOUNT` (required) — Amount 0-100
- `--clip` (optional) — Timeline audio clip name or id to target; defaults to the first current-timeline audio clip

## Boundaries and gotchas

- The accepted range is inclusive 0–100.
- The help text also says `--clip` accepts a name or ID.
- Duplicate names are not reported as ambiguous; a same-named video item can win even though this command is under `fairlight ai`.
- Matching is case-insensitive and includes item/media-pool names, selected file/path properties and basenames.
- It does not verify the UI checkbox visually or analyze rendered audio.

## DaVinci Resolve editions

It did not prove feature licensing/model availability on every Studio/Free build or acoustic quality on arbitrary material.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight ai voice-isolation --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
