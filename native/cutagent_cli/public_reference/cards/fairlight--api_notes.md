# `fairlight api-notes`

Syntax: `cutagent fairlight api-notes`

## Search terms

- what Fairlight operations can CutAgent CLI do
- unsupported Fairlight scripting features
- check Fairlight command coverage
- can CutAgent change Fairlight plugin slots
- FlexBus scripting limitations

## What it does

Check Fairlight feature availability.

## Do not use when

Do not use this command to decide whether one specific invocation will work on the current machine. Use `fairlight info`, `fairlight tracks`, bus/effect/automation readers or a command-specific getter for actual project state.
Do not use it as a full command catalog. The broad sentences do not enumerate arguments, scope, targeting or verification guarantees. Search the relevant command cards after choosing a family.

## Preflight and readback

No project preflight is required because the command is static.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- `--dry-run` is not a different plan.
- It does not promise arbitrary non-main bus/FlexBus fader mutation.

## Examples

- `cutagent fairlight api-notes --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
