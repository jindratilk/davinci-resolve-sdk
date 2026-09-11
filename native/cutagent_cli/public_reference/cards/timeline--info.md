# `timeline info`

Syntax: `cutagent timeline info`

## Search terms

- inspect current timeline
- timeline resolution fps duration
- current sequence details
- timeline start timecode and playhead
- count tracks on timeline
- is timeline empty
- timeline frame range
- verify active timeline settings

## What it does

Read the current timeline.

## Do not use when

Do not use `timeline info` when no active timeline is guaranteed; use `status` or `timeline list` first. Do not use its counts to identify clips or track names; use `timeline items` and `timeline track-list`. Do not use it as a complete settings dump; `timeline settings-get` covers additional keys. Do not infer GUI-selected/current clip from this command; use explicit item-at/current-item readbacks with their documented limitations. Do not use an empty-duration note as proof that the Media Pool is empty; it describes only the active timeline.

## Preflight and readback

Before structural edits, record track counts, playhead, start frame, and duration. After adding/deleting tracks or items, changing settings, setting start timecode, or moving the playhead, rerun and compare only the relevant fields; use item/marker/property readbacks for more specific changes.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command requires an active timeline and fails rather than returning a project-only partial result.

## Examples

- `cutagent timeline info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
