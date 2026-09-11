# `media flag clear`

Syntax: `cutagent media flag clear NAME [COLOR]`

## Search terms

- clear Media Pool flag
- remove one colored flag
- clear all clip flags
- unflag source media
- remove red review flag
- reset asset flags
- clear footage review labels
- remove every Media Pool flag

## What it does

Clear flags from a clip.

## Do not use when

Use `media color clear` when the item has an organizational clip color rather than a flag. Use `media marker delete` for frame-based source markers. Supply a color when other flags must survive; omitting it deliberately removes all colors found on the source item.

## Preflight and readback

Choose specific-color mode for surgical removal and all-flags mode only after preserving any colors that matter.

## Public arguments and options

- `NAME` (required) — Clip name
- `COLOR` (optional) — Flag color to clear (all if not specified)

## Boundaries and gotchas

- The optional positional color changes semantics: `media flag clear NAME red` removes only Red; `media flag clear NAME` loops over every currently returned flag.
- Clearing source flags does not clear clip color.

## Examples

- `cutagent media flag clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
