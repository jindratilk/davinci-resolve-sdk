# `bulk lut-set`

Syntax: `cutagent bulk lut-set NODE_INDEX LUT_PATH [--track-type VALUE] [--track VALUE] [--name VALUE] [--name-starts-with VALUE] [--name-contains VALUE] [--name-regex VALUE] [--duration VALUE] [--min-duration VALUE] [--max-duration VALUE] [--from VALUE] [--to VALUE] [--clip-color VALUE] [--state VALUE] [--limit VALUE] [--fail-fast]`

## Search terms

- apply LUT to multiple timeline clips
- batch set node LUT
- put same look on matching edits
- set color transform LUT across track
- apply cube file to selected clips
- bulk assign LUT to node one
- color grade multiple occurrences with LUT
- set installed DaVinci Resolve LUT in bulk

## What it does

Apply a LUT to clips in bulk.

## Do not use when

Use Media Pool/input-LUT commands when camera/input interpretation should follow the source everywhere. Use single-node `color node lut-set` for one clip, LUT install/refresh commands when only library registration is intended, and grade-copy/DRX/gallery commands for a complete multi-node grade. Do not use this when matched clips have different graph structures unless the same node index is semantically correct for all.

## Preflight and readback

Confirm the LUT exists in a recognized root or inspect any local-file installation consequences; render/check color management compatibility. Record original LUT paths so assignments can be restored individually.

## Public arguments and options

- `NODE_INDEX` (required) — 1-based color node index to receive the LUT
- `LUT_PATH` (required) — LUT path (absolute, or relative to the Resolve LUT root)
- `--track-type` (optional, default: `"video"`) — Track type to search: video, audio, subtitle, or all.
- `--track` (optional) — Only clips on this 1-based track index.
- `--name` (optional) — Exact clip name match.
- `--name-starts-with` (optional) — Clip name prefix match (case-sensitive).
- `--name-contains` (optional) — Clip name substring match (case-insensitive).
- `--name-regex` (optional) — Clip name regular expression match.
- `--duration` (optional) — Exact clip duration: seconds ('4' / '4s'), frames ('96f'), or timecode.
- `--min-duration` (optional) — Minimum clip duration (same formats as --duration).
- `--max-duration` (optional) — Maximum clip duration (same formats as --duration).
- `--from` (optional) — Only clips overlapping a record-domain range start (timecode, seconds, frames).
- `--to` (optional) — Only clips overlapping a record-domain range end (timecode, seconds, frames).
- `--clip-color` (optional) — Only clips currently flagged with this clip color.
- `--state` (optional) — Only clips in this state: enabled or disabled.
- `--limit` (optional, default: `500`) — Safety cap on selected clips.
- `--fail-fast` (optional, default: `false`) — Stop at the first failing clip instead of continuing.

## Boundaries and gotchas

- Node index must be at least 1, but existence is checked only per item.
- Matching audio/subtitle items with `--track-type all` is usually wrong because they may lack a color node graph.

## Examples

- `cutagent bulk lut-set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
