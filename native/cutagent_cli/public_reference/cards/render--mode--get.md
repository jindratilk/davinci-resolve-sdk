# `render mode get`

Syntax: `cutagent render mode get`

## Search terms

- get render mode
- individual clips render mode
- single clip render mode
- Deliver render mode
- mode 0 individual
- mode 1 single
- inspect current render mode

## What it does

Read current render mode.

## Do not use when

Do not infer render range, naming, output settings, or queue behavior from render mode alone.

## Preflight and readback

Before changing render mode, run this command and preserve both raw mode and description along with the current Deliver settings.
After `render mode set`, run it again and require the expected raw value. Then inspect the Deliver page and a safely queued test job because mode affects clip segmentation/naming behavior.
If `description` is unknown, retain the raw JSON value and DaVinci Resolve version/edition for diagnosis.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- No command-specific dry-run branch exists.
- The command does not open the Deliver page.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render mode get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
