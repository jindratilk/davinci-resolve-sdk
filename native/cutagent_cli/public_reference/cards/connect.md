# `connect`

Syntax: `cutagent connect`

## Search terms

- can CutAgent reach DaVinci Resolve
- scripting bridge smoke test
- external scripting connected
- embedded bridge connected

## What it does

Test the DaVinci Resolve connection.

## Do not use when

Do not use it for editing orientation; `context` requires a timeline and adds playhead/page/track facts.

## Preflight and readback

If project or timeline is null, use `status` and then explicitly open/switch the intended object.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Frame rate appears only when a current timeline exists.

## Examples

- `cutagent connect --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
