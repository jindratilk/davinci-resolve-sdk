# `fairlight send set`

Syntax: `cutagent fairlight send set [--track VALUE] [--send VALUE] [--level VALUE] [--pre-fader]`

## Search terms

- set Fairlight send level
- send A1 to reverb bus
- create aux send
- route dialogue to Bus 1
- make send pre-fader
- change send to post-fader
- lower reverb send
- assign track send destination
- add bus send on track
- change Fairlight send tap point
- control send pan or mute
- configure headphone aux send

## What it does

Check Fairlight send availability.

## Do not use when

Configure actual sends in DaVinci Resolve's Fairlight mixer when a track/bus must feed reverb, cue/headphone, parallel processing, or another destination. Verify the exact source, destination, slot, level, pre/post tap, pan and mute/bypass visually and audibly.
Its candidate destinations are not proof of active send slots and cannot verify a manual set.
Use direct track fader/gain, bus/Main level, clip gain, or routing commands when that is what the user actually requested. A send level controls a parallel feed and is not equivalent to source-track loudness or destination-bus output.
Use `fairlight preset apply` only if `fairlight preset list` exposes an exact prepared preset and broad timeline preset changes are acceptable.

## Preflight and readback

For a real manual edit, save/checkpoint the project, identify the active timeline, source track, destination bus, existing slot assignment, level, pre/post state, pan, mute/bypass and downstream bus processing. Use a controlled signal and note the original values.
After manual configuration, confirm the visible slot assignment and tap state, observe pre/post-fader behavior by moving the source fader, meter the destination, and audition/render the wet/dry mix. Restore the original send if the change was diagnostic.
Do not treat echoed request values as actual mixer state.

## Public arguments and options

- `--track/-t` (optional) — Audio track index
- `--send` (optional) — Send/bus name or slot
- `--level/--level-db` (optional) — Send level in dB
- `--pre-fader/--post-fader` (optional) — Requested send tap point

## Boundaries and gotchas

- `--pre-fader` serializes `true`.
- `--send` is not normalized, looked up, or distinguished as a name versus slot.
- The CLI parses a float but applies no Fairlight send-level range or quantization because no setter is called.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight send set --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
