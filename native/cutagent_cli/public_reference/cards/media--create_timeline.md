# `media create-timeline`

Syntax: `cutagent media create-timeline TIMELINE_NAME CLIPS...`

## Search terms

- create timeline from Media Pool clips
- assemble clips into new sequence
- make stringout timeline
- create audio timeline from sources
- put selected clips end to end
- build timeline in clip order
- create rough sequence from bins
- turn media list into timeline

## What it does

Create a timeline from clips.

## Do not use when

Use `timeline create` for an empty sequence or when width/height/fps settings are the concern. Use `media append` or `media append-batch` for exact tracks, source subranges, gaps, record frames, multiple target timelines, or per-item names. Do not use this when existing timeline material must remain and receive additional clips—the command always creates a new timeline.

## Preflight and readback

Exact-search every source and retain folder/source identity, then order the names deliberately. Record the active timeline and project timeline settings. After creation, use `timeline list` to prove the new timeline exists and is current, then inspect every relevant track for item order, names, IDs, source paths, starts, ends, and duration. Explicitly switch back if the user should remain on the prior timeline.

## Public arguments and options

- `TIMELINE_NAME` (required) — Timeline name
- `CLIPS` (required, repeatable) — Clip names

## Boundaries and gotchas

- At least one clip argument is required by the CLI.
- Same-name objects in different bins can be ambiguous; the command has no per-clip folder/path selector.
- Dry-run does not connect or resolve clip identities; it only echoes timeline name and clip count.

## Examples

- `cutagent media create-timeline --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
