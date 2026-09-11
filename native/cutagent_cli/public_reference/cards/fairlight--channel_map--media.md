# `fairlight channel-map media`

Syntax: `cutagent fairlight channel-map media CLIP`

## Search terms

- inspect source asset audio channels
- check whether media is mono or stereo
- show embedded audio channel assignment
- see which source channels a clip exposes
- inspect clip attributes audio mapping
- verify source channel layout
- check linked audio mapping
- diagnose wrong left right source channels

## What it does

Read audio channel mapping for a media pool item.

## Do not use when

Use `fairlight channel-map clip` when the intended subject is a TimelineItem or a mapping changed on one timeline instance.
First enumerate or otherwise identify the exact item name and folder.
Do not use this getter as proof of audible channel content. Render or audition the result when channel content matters.

## Preflight and readback

Before reading, identify the exact Media Pool item name and its folder. Distinguish that name from a TimelineItem's custom display name and from the filename shown in the source path. If duplicates may exist, establish which Media Pool folder is current or make the target name unique.
Compare with `fairlight channel-map clip` after placing the asset on a timeline, and render or audition the relevant channels when the mapping will drive an edit.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Boundaries and gotchas

- Matching is exact and case-sensitive.
- A source basename is accepted only if an actual Media Pool item has exactly that name.
- This makes the same command text context-dependent when duplicate names exist in different folders.
- Multiple same-name items returned inside the current folder are not reported as ambiguous; the first returned item wins.
- The success response echoes the requested text in `clip`; it does not return the resolved folder, Media Pool ID or source path.
- A successful response therefore cannot by itself prove which duplicate was read.
- Readback does not validate audio samples.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight channel-map media --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
