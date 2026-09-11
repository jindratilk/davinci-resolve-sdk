# `media flag add`

Syntax: `cutagent media flag add NAME COLOR`

## Search terms

- add flag to Media Pool clip
- mark source clip red
- flag footage for review
- add multiple colored flags
- tag asset with blue flag
- put review flag on media
- mark a bin clip as selected take
- color flag source media

## What it does

Add a flag to a clip.

## Do not use when

Use `media color set` for the item's single organizational clip color. Use `media marker add` when the annotation belongs to a source frame with a name/note/duration. Use timeline clip-flag commands when only a timeline occurrence, rather than the shared Media Pool item, should be flagged.

## Public arguments and options

- `NAME` (required) — Clip name
- `COLOR` (required) — Flag color (e.g., Blue, Red, Green)

## Boundaries and gotchas

- Input is case-insensitive after trimming; unrecognized colors fail validation rather than being approximated.
- The command verifies only membership of the requested color, not whether it was newly added.
- A Media Pool flag may be visible on timeline occurrences of the same source, but this command targets the source item and does not enumerate or verify every occurrence.

## Examples

- `cutagent media flag add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
