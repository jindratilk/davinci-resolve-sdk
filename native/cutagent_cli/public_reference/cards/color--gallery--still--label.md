# `color gallery still label`

Syntax: `cutagent color gallery still label SELECTOR [--set VALUE] [--album VALUE]`

## Search terms

- label gallery still
- rename saved grade still
- get still label
- name captured reference frame
- relabel DRX look in album
- find or set Color gallery still name

## What it does

Check a still label.

## Do not use when

Use `gallery album rename` for the containing album, `gallery still export` to choose an output filename, and grade/version commands to label or manage timeline grade versions. Do not use labels as unique IDs without checking the whole still list; duplicates are permitted and selector resolution chooses the first.

## Preflight and readback

Preserve the index too until the list changes.

## Public arguments and options

- `SELECTOR` (required) — Still selector (index or label)
- `--set` (optional) — Set still label
- `--album` (optional) — Album name or 1-based index

## Boundaries and gotchas

- Blank/whitespace labels are rejected, so this command cannot clear a label back to empty even though freshly grabbed stills commonly have empty labels.
- Numeric selector strings always mean one-based indices.
- A still labeled `1` cannot be selected by that label when index 1 exists.
- Label matching is exact first then case-insensitive.
- Set verification is case-sensitive exact equality, even though later selector matching is case-insensitive.
- Relabeling does not rename a DRX/PNG/JPG already exported from the still or the temporary DRX generated during apply.

## Examples

- `cutagent color gallery still label --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
