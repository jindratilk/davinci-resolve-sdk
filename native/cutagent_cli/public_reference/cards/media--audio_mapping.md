# `media audio-mapping`

Syntax: `cutagent media audio-mapping CLIP`

## Search terms

- inspect source audio mapping
- see mono stereo channel mapping
- get embedded audio channels
- check linked audio map
- inspect Media Pool track mapping
- find muted source channels
- verify clip audio layout

## What it does

Check source audio mapping for a media pool item.

## Do not use when

Do not use this for timeline track format, output-bus routing, clip volume, Fairlight channel mapping, or synced-audio execution. Use the corresponding timeline/Fairlight/audio commands. Do not assume the Media Pool mapping equals how a particular timeline item was routed after editing.

## Preflight and readback

Identify the exact Media Pool item and inspect its basic type/channel properties. Re-run after source audio mapping/sync/link changes and compare both embedded count and every track entry.

## Public arguments and options

- `CLIP` (required) — Media Pool clip name

## Boundaries and gotchas

- Agents must perform a second JSON parse when the first character is `{`/`[`.

## Examples

- `cutagent media audio-mapping --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
