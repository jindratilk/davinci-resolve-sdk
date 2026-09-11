# `fairlight info`

Syntax: `cutagent fairlight info INDEX`

## Search terms

- inspect Fairlight audio track
- show A1 details
- check audio track enabled state
- check whether audio track is locked
- count clips on one audio track
- show Fairlight bus context
- inspect track display height
- diagnose missing mixer lanes
- preflight one audio track

## What it does

Check audio track details.

## Do not use when

Use `fairlight tracks` or `fairlight index tracks` for all-track inventory and comparison; this command accepts exactly one index. Do not use bus labels in this result to infer this track's routing; they are timeline-wide label-pool context, not a track-to-bus graph.

## Preflight and readback

Before reading, activate and preferably save the intended local Disk timeline; use `fairlight tracks` when the index/name mapping is uncertain. No post-mutation verification is required because the command is read-only.

## Public arguments and options

- `INDEX` (required) — Track index

## Boundaries and gotchas

- Global dry-run never connects or validates that the track exists.

## Examples

- `cutagent fairlight info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
