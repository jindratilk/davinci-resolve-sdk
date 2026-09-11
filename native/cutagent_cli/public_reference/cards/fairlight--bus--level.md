# `fairlight bus level`

Syntax: `cutagent fairlight bus level [BUS] [--level VALUE]`

## Search terms

- set timeline output level
- change Bus 1 level
- lower Main bus
- adjust Main 1 gain
- inspect Fairlight bus level
- change timeline main volume
- set default output gain context
- check Main bus fader value

## What it does

Check and update main-output sequence gain.

## Do not use when

Do not use this command as proof of a Main/FlexBus mixer fader setting.
Do not use it for `Bus 2`, arbitrary buses or FlexBuses; those storage/routing paths are unmapped. Use `fairlight bus list` only to inspect label evidence, not as a setter.
Use clip gain commands for individual TimelineItems, track mixer commands for an audio channel strip, and automation commands for time-varying level. `fairlight automation write --bus Main` currently delegates to this same sequence-output field and has the same limitation.
Do not use the setter on cloud/PostgreSQL project libraries or when a save/close/reopen cycle would disrupt an active edit, playback, render or recording.

## Preflight and readback

Before reading or writing, make the exact target timeline active and record its name/sequence.
After a set, require the intended project and timeline—not `Untitled Project`—to reopen. Audition/render through the intended output and inspect the Fairlight UI before claiming audible/fader equivalence.

## Public arguments and options

- `BUS` (optional) — Bus name, e.g. 'Bus 1' or 'Main 1'
- `--level/--level-db` (optional) — Target bus level in dB, e.g. -6.0

## Boundaries and gotchas

- Only the Bus1/Main/Main1 family survives it.
- Do not promise more than one decimal.
- This can make output larger and still does not prove routing or fader state.
- That does not mean arbitrary bus routing is supported.
- There is no `--timeline` option.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight bus level --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
