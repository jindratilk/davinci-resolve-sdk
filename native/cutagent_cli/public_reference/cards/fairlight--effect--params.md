# `fairlight effect params`

Syntax: `cutagent fairlight effect params [EFFECT] [--track VALUE] [--clip VALUE] [--bus VALUE] [--param VALUE]`

## Search terms

- inspect Gain value on audio clip
- get Voice Isolation dry mix
- show clip plugin settings
- list available parameter names
- check Dialogue Leveler controls
- inspect Dynamics or EQ state
- find BMD plugin parameter token
- verify audio effect setting

## What it does

Read Fairlight clip FX parameters.

## Do not use when

Do not use it to enumerate the whole chain; use `fairlight effect list --clip NAME`. Use `fairlight dynamics read` or `fairlight eq read` when the request is explicitly about those built-in timeline processors and their domain-specific fields.

## Preflight and readback

First run `fairlight effect list --clip NAME` to prove the requested plugin is on the intended unique clip and capture its exact parameter names. Save the project if the GUI just changed the effect.

## Public arguments and options

- `EFFECT` (optional) — Fairlight effect/plugin name or slot identifier
- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Timeline clip name to target
- `--bus` (optional) — Bus name to target
- `--param` (optional) — Specific parameter name to inspect

## Boundaries and gotchas

- Always provide `--clip` in multi-clip timelines.
- Readability does not imply writability.
- Parameter matching strips punctuation and allows the suffix after `::`; this is convenient but can become ambiguous if a plugin contains multiple namespaces with the same suffix.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight effect params --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
