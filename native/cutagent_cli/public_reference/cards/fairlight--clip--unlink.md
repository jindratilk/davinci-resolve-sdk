# `fairlight clip unlink`

Syntax: `cutagent fairlight clip unlink CLIP_NAME`

## Search terms

- unlink audio clip
- break linked clips
- detach Fairlight clip from group
- separate linked audio items
- stop audio clips moving together
- unlink audio from video
- remove clip link relationship
- break sync link
- dissolve clip link group
- detach dialogue from linked item
- make clip independent

## What it does

Unlink a Fairlight timeline clip through the DaVinci Resolve.

## Do not use when

Use `fairlight clip link` when creating or rebuilding a desired link group.
Use `fairlight clip linked list` when only inspecting membership. `unlink` is a mutation and its built-in readback is narrower than a full group audit.
Do not use this to detach a media-pool asset, separate embedded audio channels, ungroup a compound/multicam clip, or remove a track routing relationship. It operates only on timeline item link state.
Do not use an ambiguous display/source name when exact occurrence matters.
Do not assume this is audio-only or an audio/video-specific sync unlink.

## Preflight and readback

Inventory names, tracks, record ranges and unique identities separately because the unlink command accepts only one text name and its output does not expose the expanded operation list.
If names repeat across video/audio or tracks, do not proceed until the intended item has a unique resolvable label; dry-run merely trims and echoes the string and cannot expose ambiguity.
Afterward, query every former member with `fairlight clip linked list`. An empty list only on the requested item is insufficient proof that the whole previous group has the desired final structure.

## Public arguments and options

- `CLIP_NAME` (required) — Audio clip name to unlink

## Boundaries and gotchas

- The command does not disclose that degraded expansion.
- If duplicate names, track contents or names change between those reads, the displayed plan and mutated object can diverge.
- Duplicate names do not produce an ambiguity error.
- It does not preserve a subgroup automatically.
- Readback objects contain only linked item name/start/end.
- They do not include track, unique ID or media type, so duplicate former members require separate inventory.
- The command acts on the active timeline only and has no `--timeline` switch.

## DaVinci Resolve editions

Free was not independently exercised for this card.

## Examples

- `cutagent fairlight clip unlink --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
