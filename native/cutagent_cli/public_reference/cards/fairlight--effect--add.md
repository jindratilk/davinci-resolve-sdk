# `fairlight effect add`

Syntax: `cutagent fairlight effect add [EFFECT] [--track VALUE] [--clip VALUE] [--bus VALUE]`

## Search terms

- add Fairlight effect to audio clip
- enable Voice Isolation on a clip
- add Gain plugin to dialogue
- put reverb on an audio clip
- apply Dialogue Leveler to one clip
- enable timeline Dialogue Processor
- add BMD audio plugin
- add Fairlight EQ processing

## What it does

Runs the public `fairlight effect add` CutAgent command.

## Do not use when

Do not use it to change a parameter of an effect already present; use `fairlight effect params` followed by `fairlight effect set-param`. Use `fairlight dynamics enable/set` when the requested operation is explicitly compressor, gate, or limiter state, and `fairlight eq set` for timeline EQ bands. Use `clip voice-isolation set` when the requested amount is not the fixed 100 used by this add command.

## Preflight and readback

Confirm that the clip name is unique in the current timeline and use global `--dry-run` to inspect the chosen route. After a clip insertion, run `fairlight effect list --clip NAME` and `fairlight effect params EFFECT --clip NAME`; for Voice Isolation also use `clip voice-isolation get`.

## Public arguments and options

- `EFFECT` (optional) — Fairlight effect/plugin name
- `--track/-t` (optional) — Audio track index to target
- `--clip` (optional) — Timeline clip name to target
- `--bus` (optional) — Bus name to target

## Boundaries and gotchas

- Omitting `--clip` changes `Dialogue Processor` into a timeline-level dynamics write.
- It does not create a new EQ slot.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight effect add --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
