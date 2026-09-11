# `fairlight clip linked list`

Syntax: `cutagent fairlight clip linked list [CLIP]`

## Search terms

- list clips linked to audio item
- inspect Fairlight clip links
- check linked audio partners
- see clip link group
- verify audio clips move together
- find linked timeline items
- inspect dialogue boom link
- check whether clip is unlinked
- show link relationship before edit
- identify linked clip starts and ends

## What it does

List timeline items linked to a Fairlight timeline clip through the DaVinci Resolve.

## Do not use when

Use `fairlight clip link` to establish a relationship and `fairlight clip unlink` to remove one.
Do not use it to determine timeline track/index, TimelineItem ID, duration, media source or channel mapping. Combine with `fairlight clip track-info`, `clip info` and channel-map readers for those facts.
Do not use a non-unique source filename/basename to prove which occurrence is linked. The first match is accepted without ambiguity checking, and an explicit alias is echoed in `clip` rather than replaced with the resolved display name.
Do not treat one member's list as complete proof of a requested N-item group.

## Preflight and readback

Before reading, identify a unique TimelineItem by name, track and range. When omitting the selector, verify the playhead and whether a current video item may take precedence.
Afterward, compare each partner's name/start/end with the timeline inventory. For an N-item group, query all N items and check that each returns the other N−1 intended members. Empty `linked` is a valid unlinked state, not an error.

## Public arguments and options

- `CLIP` (optional) — Clip name (current clip when omitted)

## Boundaries and gotchas

- Explicit matching includes source/Media Pool aliases and case-insensitive basenames.
- Only when it is absent does playhead scanning consider audio.
- The command does not compute transitive closure or infer groups from overlapping timestamps.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent fairlight clip linked list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
