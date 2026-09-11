# `fairlight effect set-param`

Syntax: `cutagent fairlight effect set-param [EFFECT] [--track VALUE] [--clip VALUE] [--bus VALUE] [--param VALUE] [--value VALUE] [--create-if-missing]`

## Search terms

- change Fairlight effect parameter
- set Gain plugin value
- adjust Voice Isolation amount
- edit clip audio FX settings
- change Dialogue Leveler control
- set Music Remixer stem level
- create effect and set parameter
- tune Chorus dry wet
- change limiter threshold on clip

## What it does

Set Fairlight clip FX parameter.

## Do not use when

Use `fairlight effect remove` to disable/remove the effect entirely. Use `fairlight dynamics set`, `fairlight eq set`, or other domain commands for timeline/track built-in processing rather than pretending it is a clip plugin. Do not pass `--track` or `--bus`; arbitrary track/bus parameter routing is unsupported.

## Preflight and readback

Run `effect list --clip NAME`, then `effect params EFFECT --clip NAME` and retain the stable clip ID, fully qualified parameter token, existing value, and sibling plugin list.

## Public arguments and options

- `EFFECT` (optional) — Known clip-level Fairlight effect/plugin name
- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Timeline clip name to target
- `--bus` (optional) — Bus name to target
- `--param` (optional) — Specific parameter name to set
- `--value` (optional) — New parameter value
- `--create-if-missing/--no-create-if-missing` (optional, default: `false`)

## Boundaries and gotchas

- Readable does not mean writable.
- Without `--clip`, the first current-timeline audio clip is used.

## Examples

- `cutagent fairlight effect set-param --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
