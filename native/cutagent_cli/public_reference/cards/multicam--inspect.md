# `multicam inspect`

Syntax: `cutagent multicam inspect [--multicam-name VALUE] [--timeline VALUE]`

## Search terms

- list multicam candidates
- inspect multicam bindings
- multicam audio binding mode
- multicam timeline segments
- manual UI verdict
- multicam binding mismatch
- dry-run requires project

## What it does

Inspect a multicam clip and its the current timeline state.

## Do not use when

There is no dry-run branch.
Do not use `--media-id` or `--sequence-id`; this command targets detail by multicam name only.

## Preflight and readback

If timeline state matters, pass the exact `--timeline` and independently confirm it exists/current.
Use the GUI and/or a render to confirm angle ordering/switching.

## Public arguments and options

- `--multicam-name` (optional)
- `--timeline` (optional) — Optional timeline name to inspect multicam segment state

## Boundaries and gotchas

- Options are `--multicam-name` and `--timeline`.
- UI labels are generated as one-based `Angle N`.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`
- `INVALID_OPTION`
- `VALIDATION_ERROR`

## Examples

- `cutagent multicam inspect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
