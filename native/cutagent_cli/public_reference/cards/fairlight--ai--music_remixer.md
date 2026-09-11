# `fairlight ai music-remixer`

Syntax: `cutagent fairlight ai music-remixer [--voice VALUE] [--drums VALUE] [--bass VALUE] [--other VALUE] [--guitar VALUE] [--clip VALUE]`

## Search terms

- rebalance music stems
- lower vocals in a song
- turn drums up
- reduce bass in music
- isolate music components
- remix voice drums bass guitar
- adjust background music instrumentation
- make instrumental from song
- change guitar level
- control Music Remixer stems
- rebalance other instruments
- apply Music Remixer to one clip

## What it does

Set AI Music Remixer stem levels.

## Do not use when

Use audio ducking when the goal is to lower an entire music bed automatically under dialogue; stem voice level is not sidechain ducking.

## Preflight and readback

Preserve all existing ClipFX/other audio processing and independently checkpoint the local Disk project.
Afterward, require the intended project/timeline to reopen. Run `fairlight ai read` against the same clip ID and compare all five stems, including omitted values and any prior plugins.

## Public arguments and options

- `--voice` (optional) — Voice stem level (0.0-1.0)
- `--drums` (optional) — Drums stem level (0.0-1.0)
- `--bass` (optional) — Bass stem level (0.0-1.0)
- `--other` (optional) — Other stem level (0.0-1.0)
- `--guitar` (optional) — Guitar stem level (0.0-1.0)
- `--clip` (optional) — Timeline audio clip name or id to target; defaults to the first current-timeline audio clip

## Boundaries and gotchas

- There are no piano, strings or ambience controls; unmatched content is represented only by `other`.
- Clip name matching is case-insensitive exact matching and rejects duplicate matches.
- Missing/ambiguous audio clips can therefore cause disruptive pre-commit recovery.
- Studio-only AI model variation is explicitly unsupported.
- Built-in verification does not check model download/licensing, UI recognition, mute states, unchanged unrelated plugins, render output, clip selection or playhead.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight ai music-remixer --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
