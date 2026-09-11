# `fairlight ai read`

Syntax: `cutagent fairlight ai read [--clip VALUE]`

## Search terms

- inspect AI audio settings
- show clip AI effects
- list audio ClipFX plugins
- check whether AI audio effect is enabled
- show Fairlight clip effect parameters
- check clean audio clip for AI effects

## What it does

Read all AI audio feature settings from the current clip.

## Do not use when

Do not interpret `found:false` as proof that a clip has no audio processing at all. Do not use this command as acoustic verification; audition/render the clip.

## Preflight and readback

Before reading, verify the active timeline and enumerate audio items.
After reading, confirm target ID/name/timeline and inspect the complete `plugins` list before using convenience summaries. Compare raw float parameters with the setter request using tolerances.

## Public arguments and options

- `--clip` (optional) — Timeline audio clip name or id to inspect; defaults to the first current-timeline audio clip

## Boundaries and gotchas

- The Python `zstandard` dependency is required.
- Music Remixer convenience output appears only when the voice-level parameter is present.

## Examples

- `cutagent fairlight ai read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
