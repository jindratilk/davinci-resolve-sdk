# `render settings-get`

Syntax: `cutagent render settings-get`

## Search terms

- get render settings
- render settings alias
- current Deliver configuration
- render readback source map
- current format codec mode
- render queue context

## What it does

Read current render settings.

## Do not use when

Do not expect behavior or fields different from `render settings`; this is a public alias, not a narrower key getter.
Do not treat the merged result as atomic or as proof that an encoder will accept the configuration.

## Preflight and readback

Before execution, make the intended project and timeline current and avoid concurrent Deliver-setting or queue changes.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The final `source` object reports only primary settings, current format/codec, current mode, and queue sources.

## Stable public error codes

- `EMBEDDED_BRIDGE_NOT_RUNNING`

## Examples

- `cutagent render settings-get --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
