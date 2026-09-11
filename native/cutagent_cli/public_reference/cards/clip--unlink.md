# `clip unlink`

Syntax: `cutagent clip unlink CLIP_NAME`

## Search terms

- unlink video and audio
- separate linked clips
- stop picture and sound moving together
- detach audio from video occurrence
- break DaVinci Resolve clip link
- edit one member independently
- remove timeline item link group
- unpair synced clips without moving them

## What it does

Unlink a clip.

## Do not use when

Use synchronization/offset commands when the relationship should remain linked but picture and sound need alignment. Use delete/extract commands when one member should be removed from the timeline. Do not expect unlinking to split media, make embedded channels into separate sources, or preserve a subgroup of a larger linked set; this command expands from one member to all links returned by that member.

## Preflight and readback

Confirm that separating selection behavior is actually intended, especially for production sync audio. Their start/end/source ranges should be unchanged. If invoked only as a dry-run, verify that membership remains present before doing any real edit.

## Public arguments and options

- `CLIP_NAME` (required) — Clip name

## Boundaries and gotchas

- Unlinking does not shift, trim, mute, disable, or delete any member.

## Examples

- `cutagent clip unlink --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
