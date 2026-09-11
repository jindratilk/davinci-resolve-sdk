# `color gallery album list`

Syntax: `cutagent color gallery album list`

## Search terms

- list gallery albums
- show still albums
- find Color page gallery folders
- get gallery album indices
- inventory project still collections
- choose album for still command

## What it does

List gallery still albums.

## Do not use when

Do not use a previously cached index as a permanent identifier: album creation/reordering outside this command can change one-based positions, so resolve the latest list immediately before an index-targeted mutation.

## Preflight and readback

Run this immediately before switch/rename or any `--album` still operation and retain both index and exact name. When a command is meant to act on the current album, pair it with `album current` rather than inferring current state from this list.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Indices are one-based and positional, not stable IDs.
- This list covers ordinary Gallery still albums only.
- Duplicate/case-variant album names are not disambiguated in the row shape.

## Examples

- `cutagent color gallery album list --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
