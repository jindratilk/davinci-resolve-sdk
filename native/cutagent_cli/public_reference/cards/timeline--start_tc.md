# `timeline start-tc`

Syntax: `cutagent timeline start-tc [VALUE]`

## Search terms

- get timeline start timecode
- change sequence start code
- set timeline hour offset
- compatibility start timecode command
- timeline begins at one hour
- rebase timeline timecode
- inspect timeline start TC

## What it does

Check timeline start timecode.

## Do not use when

Do not use it to move the playhead, change a source clip's timecode, set Media Pool metadata, or shift clips. Do not supply a value when only inspecting state—the same command path will mutate.

## Preflight and readback

If setting through the alias, validate HH:MM:SS:FF against timeline fps, checkpoint/export when absolute time references matter, then run the no-value form and `timeline info`/playhead readback. Restore the original start code after temporary tests.

## Public arguments and options

- `VALUE` (optional) — Optional new start timecode

## Boundaries and gotchas

- The optional positional value changes the command from read-only to mutating; omission versus presence is semantically critical.
- There is no separate `--set` flag and no visible dry-run branch on the alias setter; a supplied value can mutate even in workflows that assumed a getter.

## Examples

- `cutagent timeline start-tc --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
