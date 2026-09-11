# `fairlight track-color`

Syntax: `cutagent fairlight track-color INDEX COLOR`

## Search terms

- set Fairlight track color
- color-code audio track
- make dialogue track blue
- change A1 color
- label music track green
- clear track color
- remove audio track color
- organize Fairlight tracks by color
- set mixer track color
- color audio lane
- mark SFX track orange
- apply DaVinci Resolve track color

## What it does

Set an audio track color.

## Do not use when

Use a clip-color command when the user wants individual timeline clips or Media Pool items colored.
Use `fairlight track duplicate --copy-color` when color should be copied as one part of creating a duplicate track. Use this command when recoloring an already existing track without duplication.
Do not use arbitrary CSS/RGB/hex names.

## Preflight and readback

Before mutation, confirm the active project/timeline and run `fairlight tracks` to resolve the current 1-based target index. Record page, playhead, selection and the existing track color visually; later track insertions/deletions can make a cached numeric index point at another track.
Do not rely on dry-run to validate the color string or track existence.

## Public arguments and options

- `INDEX` (required) — Track index
- `COLOR` (required) — DaVinci Resolve Fairlight track color name, e.g. Apricot, Blue, Green, or Clear

## Boundaries and gotchas

- Color names are case-insensitive, but dry-run echoes the original spelling and never normalizes or rejects it.
- The CLI validates `index >= 1` before dry-run, but dry-run does not verify that the track exists.
- Do not use it as a cheap read-only color query.
- This changes track color only.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight track-color --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
