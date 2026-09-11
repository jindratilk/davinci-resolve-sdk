# `audio voice-place`

Syntax: `cutagent audio voice-place PATH --track VALUE --absolute-record-frame VALUE`

## Search terms

- place generated voiceover exactly
- import retained narration mp3
- append exact voice asset to audio track
- generated voice timeline record frame

## What it does

Import one generated voice asset and place that exact media pool item.

## Do not use when

Do not use this for arbitrary user media, approximate placement, a locked or unknown-lock-state track, a stale timeline revision, or before the user-owned SDK mutation scope has authorized the exact project, timeline, track, and frame. Do not infer that the spoken result is editorially acceptable from structural placement readback.

## Preflight and readback

Before running, verify the retained asset digest, current project and timeline identities, current timeline revision, target audio track index, explicit unlocked state, and absolute record frame. Audition separately when activation evidence or final editorial approval requires it.

## Public arguments and options

- `PATH` (required) — Retained generated-voice MP3 path
- `--track` (required) — One-based target audio track
- `--absolute-record-frame` (required) — Exact DaVinci Resolve API recordFrame

## Boundaries and gotchas

- The command accepts only MP3 files and requires exactly one imported Media Pool item.
- The target is always audio-only and `--track` is one-based.

## Examples

- `cutagent audio voice-place --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
