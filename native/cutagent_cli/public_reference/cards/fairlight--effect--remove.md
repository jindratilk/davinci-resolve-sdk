# `fairlight effect remove`

Syntax: `cutagent fairlight effect remove [EFFECT] [--track VALUE] [--clip VALUE] [--bus VALUE]`

## Search terms

- remove Fairlight effect from audio clip
- delete clip audio FX
- turn off Voice Isolation
- remove Gain plugin from clip
- disable timeline Dialogue Processor
- remove BMD audio effect
- take reverb off a clip
- delete Fairlight track plugin
- restore clip with no audio effects

## What it does

Runs the public `fairlight effect remove` CutAgent command.

## Do not use when

Disable Voice Isolation first with this command or `clip voice-isolation set`, then remove the remaining single generic effect. Do not try to remove plain EQ; use `fairlight eq set/read` to change or neutralize its bands.

## Preflight and readback

Run `fairlight effect list --clip NAME` before removal and require the requested plugin to be present. Confirm the clip name is unique and checkpoint a disposable/test project because the project closes and reopens.

## Public arguments and options

- `EFFECT` (optional) — Fairlight effect/plugin name or slot identifier
- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Timeline clip name to target
- `--bus` (optional) — Bus name to target

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`
- `VALIDATION_ERROR`

## Examples

- `cutagent fairlight effect remove --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
