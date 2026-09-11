# `media unlink`

Syntax: `cutagent media unlink NAME`

## Search terms

- unlink Media Pool clip from source
- detach project clip from disk file
- remove source link without deleting clip
- break media file association
- unlink timeline-used media

## What it does

Unlink clip from source media.

## Do not use when

Use `media delete` when the Media Pool object itself should be removed; deletion can leave timeline items without any Media Pool ID, whereas unlink keeps a relinkable object. Use `media replace` when changing directly to a known different source file. Use proxy unlink through `media proxy --unlink` when only the proxy association should be removed while full-resolution media stays online.

## Public arguments and options

- `NAME` (required) — Clip name

## Boundaries and gotchas

- Same-source duplicates are independent Media Pool objects; unlinking one does not automatically unlink the others.

## Examples

- `cutagent media unlink --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
