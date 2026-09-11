# `color gallery album current`

Syntax: `cutagent color gallery album current`

## Search terms

- show current gallery album
- which still album is selected
- get active Color gallery folder
- verify gallery album switch
- current album index and name

## What it does

Read current gallery album.

## Do not use when

Use `color gallery album list` for a compact inventory when current selection is irrelevant, `album switch` to change selection, and `gallery still list` to inspect contents. Do not use this to infer the current clip or Color-page node; Gallery album selection is independent of timeline clip selection.

## Preflight and readback

Run before any still command that omits `--album`, because that command will target this album. For automation, retain the explicit album name and pass it to subsequent still commands instead of relying on mutable UI selection.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Duplicate albums with equal case-folded names can therefore make current identification ambiguous.

## Examples

- `cutagent color gallery album current --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
