# `timeline media-pool-item`

Syntax: `cutagent timeline media-pool-item`

## Search terms

- current timeline Media Pool item
- timeline backing clip
- nested timeline media item
- Media Pool timeline identity
- get timeline source object
- timeline bin item

## What it does

Check the source clip for the current timeline item.

## Do not use when

Do not use this command to find the clip under the playhead, the selected timeline item, a clip's source Media Pool item, or an item at a record frame. It never scans timeline tracks.
Do not use the returned `item` field as a stable machine identifier.

## Preflight and readback

Before execution, activate the exact timeline whose own Media Pool representation is needed. If the intended target is a clip on that timeline, choose an item-selection command first instead.
After execution, verify the returned `name` against the active timeline and Media Pool. For durable correlation, follow up with a command that exposes a stable Media Pool id/path; do not persist or compare the textual `item` proxy.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- There is no `--timeline` option; activate another timeline separately before calling it.
- The command does not return Media Pool id, unique id, folder, path, clip properties, source type, timeline index, duration, or usage locations.
- The command does not change current timeline, project, Media Pool, or timeline contents.

## Stable public error codes

- `API_CALL_FAILED`
- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline media-pool-item --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
