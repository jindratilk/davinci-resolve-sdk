# `clip flag`

Syntax: `cutagent clip flag [NAME] [--add VALUE] [--clear]`

## Search terms

- flag a timeline clip
- add green flag to clip
- mark a source clip for review
- list clip flags
- clear all clip flags
- tag selects with colored flags
- find flagged footage workflow
- add multiple colored flags

## What it does

Manage clip flags.

## Do not use when

Use `clip color` for the single editorial color strip on a timeline occurrence. Use clip/media marker commands when the annotation belongs at a frame or range and needs a name, note, or duration.

## Preflight and readback

After any attempted clear, require the list to be empty rather than trusting the message.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--add` (optional) — Add flag color
- `--clear` (optional, default: `false`) — Clear all flags

## Boundaries and gotchas

- `--clear` offers no color argument, so it cannot request removal of one color; the media command can.
- `--add` and `--clear` cannot be combined.
- Duplicate timeline names are resolved to the first match, with no track/time selector.

## Examples

- `cutagent clip flag --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
