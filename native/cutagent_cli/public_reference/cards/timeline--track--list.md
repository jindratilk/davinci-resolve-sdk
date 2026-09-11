# `timeline track list`

Syntax: `cutagent timeline track list`

## Search terms

- list timeline tracks
- inspect video audio subtitle tracks
- track enabled locked state
- count items per track
- active timeline structure
- timeline tracks alias
- verify track indexes

## What it does

List all tracks.

## Do not use when

Do not parse `enabled` and `locked` as booleans. This command intentionally returns UI symbols.

## Preflight and readback

Before execution, activate the intended timeline and clear modal dialogs. Re-run this command immediately before any index-addressed operation because add/delete actions can renumber tracks.
After execution, map type+index to name and item count; interpret the symbols carefully; use track-items/subtype or narrower state commands when stronger evidence is needed; and refresh after every structural mutation.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- On large timelines this can be substantially more expensive than count/name-only inspection.
- The command does not return item identities or frame positions.
- Machine-mode help on the hidden alias path is not reliable; use canonical `timeline track list --help`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent timeline track list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
