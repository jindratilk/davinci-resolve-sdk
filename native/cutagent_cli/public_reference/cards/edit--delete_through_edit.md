# `edit delete-through-edit`

Syntax: `cutagent edit delete-through-edit [--at VALUE] [--track-type VALUE] [--track VALUE] [--tolerance-frames VALUE]`

## Search terms

- delete through edit
- remove redundant cut
- join two split clip halves
- heal edit point
- merge adjacent same-source clips
- remove razor cut without ripple
- rejoin bladed clip
- eliminate invisible cut
- heal contiguous source segments
- combine two halves of one clip
- remove edit but keep timing
- restore clip after accidental blade

## What it does

Delete a through edit by merging adjacent same-source clip segments.

## Do not use when

Use `edit blade`/`edit split` to create an edit, trim commands to move an edge, or ripple-delete commands to remove material and close time. Use a compound clip or explicit clip/group workflow when distinct adjacent clips should become one editorial object but are not contiguous ranges of the same source. Use transition removal when the visible seam is a transition rather than a through edit.
Do not use this merely because adjacent items have the same filename: they must resolve to the same Media Pool identity and continuous source ranges.

## Preflight and readback

Use a narrow `--track`; position `--at` at the edit boundary rather than inside a clip, and keep tolerance zero unless a measured offset is intentional.
Afterward, require the intended project and timeline—not `Untitled Project`—to reopen. Independently list the touched video/audio tracks and prove there is one item spanning the exact former union, the old boundary is absent, source playback remains continuous and no neighboring item moved. Inspect/render both sides of the former boundary for lost right-half effects, grades, markers, retiming or audio processing.

## Public arguments and options

- `--at` (optional) — Edit-point position (default: playhead)
- `--track-type` (optional, default: `"video"`) — Track type: video, audio
- `--track` (optional, default: `0`) — Track index (0 = search all)
- `--tolerance-frames` (optional, default: `0`) — Accept an edit point within N frames

## Boundaries and gotchas

- Dry-run exits before connecting.
- Only `video` and `audio` are accepted.
- `--track 0` means all tracks of that one type, not track zero.
- This convenience can be ambiguous when the containing clip has candidates on both sides.
- `--tolerance-frames` selects the nearest boundary within the radius.
- With track 0, equally near candidates on different tracks are rejected as ambiguous; a large tolerance can still target a different edit than the agent intended.
- It does not compare the halves' grades, transforms, opacity, speed maps, Fusion/OFX, markers, clip names, color, flags, audio gain/EQ or other row payloads.
- Right-half-only metadata/effects are therefore not merged and can disappear even though the source seam qualifies as a through edit.
- If both heuristic opposite-kind halves exist, they are merged automatically even when the user requested only video or only audio.
- Track lock state is not checked and there is no `--ignore-locks` switch.
- Verification does not reread source In/out, media identity, right-half effects, markers, track index order in the GUI or pixel/audio continuity.
- The command does not intentionally restore playhead or selection.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent edit delete-through-edit --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
