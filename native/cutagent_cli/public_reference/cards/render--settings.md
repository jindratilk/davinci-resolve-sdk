# `render settings`

Syntax: `cutagent render settings`

## Search terms

- show render settings
- Deliver settings readback
- current format codec mode
- render queue count
- render settings source diagnostics
- timeline output resolution context

## What it does

Read current render settings.

## Do not use when

Do not assume every absent field is unset.

## Preflight and readback

Before execution, ensure the intended project and timeline are current and no concurrent action is changing Deliver settings or the render queue.
After a write, rerun this command and compare the relevant concrete keys rather than only checking command success. Also inspect the Deliver page and perform a short render for settings that affect encoded media.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Each project setting is added only if the same output key is not already present.
- The command does not expose every Deliver-page setting supported by every DaVinci Resolve version.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render settings --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
