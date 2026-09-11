# `media color clear`

Syntax: `cutagent media color clear NAME`

## Search terms

- clear Media Pool clip color
- remove clip color label
- reset source clip color
- uncolor footage in bin
- remove organizational color
- restore default Media Pool color
- clear asset color coding

## What it does

Clear clip color.

## Do not use when

Use `media flag clear` to remove one or all flags; clearing clip color leaves flags untouched. Use timeline-item color clearing when the intended target is one timeline occurrence. Do not use this to reset grading or LUT state—clip color here is Media Pool organization, not picture processing.

## Preflight and readback

After the command, require `Clip Color` to be an empty string/default while independently confirming any flags that should remain. If the previous color matters, record it before clearing because the response carries no prior value or undo hint.

## Public arguments and options

- `NAME` (required) — Clip name

## Boundaries and gotchas

- The command reports changed success even when no color may already be set; it does not distinguish an idempotent no-op.
- Clearing source clip color can affect how the Media Pool item is shown across bins/uses, but it does not intentionally clear timeline-local clip colors.
- The operation does not expose the old color, create a checkpoint, or offer a restore option.

## Examples

- `cutagent media color clear --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
