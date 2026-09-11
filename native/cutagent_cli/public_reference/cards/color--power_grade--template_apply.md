# `color power-grade template-apply`

Syntax: `cutagent color power-grade template-apply TEMPLATE [--clip VALUE] [--mode VALUE]`

## Search terms

- apply a PowerGrade template to a clip
- use a named PowerGrade template
- load a reusable Color look by label
- apply Gallery template to current clip
- copy full PowerGrade node graph
- use PowerGrade template mode 0
- apply saved grade body from User Gallery
- put a PowerGrade preset on footage
- apply PowerGrade by path-like name
- replace clip grade with named template
- transplant reusable DaVinci Resolve grade
- use a template-style PowerGrade selector

## What it does

Runs the public `color power-grade template-apply` CutAgent command.

## Do not use when

Use `color gallery still apply` for a still in the currently selected ordinary Gallery album. Do not request modes 1 or 2 for selective application: they are exposed in help but intentionally rejected.

## Preflight and readback

Confirm the clip name is unique, the representative midpoint can render, and temporary Color/Deliver proof output is possible. Record the current playhead and render state independently because an error after the before-proof may bypass the normal restoration path.
Check that the original timeline, project, playhead, render settings and render jobs were restored.

## Public arguments and options

- `TEMPLATE` (required) — PowerGrade template selector, label, or path-like name
- `--clip` (optional) — Target clip
- `--mode` (optional, default: `0`) — Full-grade mode: 0 only

## Boundaries and gotchas

- “Template” is naming only.
- Although `--help` advertises `--mode` values 0, 1 and 2, only 0 is implemented.
- Mode is validated even in dry-run.
- Digit-only labels cannot be forced to label semantics.
- Both visual checks only demand some nonzero RGB24 difference.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent color power-grade template-apply --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
