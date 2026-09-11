# `fairlight eq read`

Syntax: `cutagent fairlight eq read`

## Search terms

- check whether audio clip has EQ
- identify clip EQ preset
- get current audio equalizer state
- verify Fairlight EQ write
- check high-pass or presence preset

## What it does

Read current EQ settings from audio clip.

## Do not use when

Do not use this command to inspect a specific named or visible clip in a multi-clip project.

## Preflight and readback

For audible or GUI confirmation, reopen the clip EQ panel or render/audition a controlled signal; this reader does not decode arbitrary bands.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- An open project with audio rows but no current timeline cannot use this route normally.
- It does not prove the bytes are valid EQ, enabled in DaVinci Resolve, or accepted audibly.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight eq read --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
