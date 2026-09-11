# `fairlight effect plugin-catalog`

Syntax: `cutagent fairlight effect plugin-catalog [--limit VALUE]`

## Search terms

- list installed Fairlight plugins
- find available audio effects
- inspect Audio Unit catalog
- list VST3 plugins seen by DaVinci Resolve
- discover BMD audio FX
- find Fairlight plugin parameter tokens
- inspect AUConfiguration XML
- inspect Fairlight FX scan paths
- check whether a plugin is enabled
- list local audio plugin inventory

## What it does

List available Fairlight AU and VST3 XML entries and built-in BMD Fairlight FX symbols.

## Do not use when

Do not use this command to list effects currently applied to a clip; use `fairlight effect list --clip NAME`. Do not confuse these audio plugins with Color Page image effects; use `color page resolvefx-list` for ResolveFX/OFX.

## Preflight and readback

Run it before choosing a third-party audio effect name or diagnosing why a plugin is missing from DaVinci Resolve's Fairlight UI. Afterward, if the job is a supported clip-level BMD effect, confirm the command's supported list with `fairlight effect list --dry-run` and inspect the target clip before adding it.

## Public arguments and options

- `--limit` (optional, default: `100`) — Maximum plugin entries per provider to read

## Boundaries and gotchas

- `--limit` is per provider, not a global result cap.
- BMD built-ins have `enabled: null` because symbol scanning cannot infer such state.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight effect plugin-catalog --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
