# `clip audio-eq`

Syntax: `cutagent clip audio-eq [NAME] [--preset VALUE] [--band VALUE] [--ui-band VALUE] [--filter-type VALUE] [--freq VALUE] [--gain-db VALUE] [--q VALUE] [--at VALUE]`

## Search terms

- EQ one timeline clip
- add presence to dialogue clip
- high pass rumble from one clip
- cut one kilohertz on audio item
- boost frequency band on linked audio
- apply clip equalizer preset
- set DaVinci Resolve clip EQ band
- notch a frequency on one occurrence
- low pass one audio clip

## What it does

Apply audio EQ to a linked clip.

## Do not use when

Use Fairlight track EQ when the whole track/bus should share processing or when several bands must be interactively managed together. Use `clip audio-gain` for broadband level, `clip audio-normalize` for peak targeting, and high/low-pass source preprocessing when the file itself must change. Use a purpose-built dialogue processing chain when compression, de-essing, noise reduction, and EQ must coexist. Do not assume arbitrary combinations are supported: choose a listed preset or validate the exact band/filter/frequency/gain/Q route first.

## Preflight and readback

Identify the exact occurrence, inspect its current clip effects, and capture a flat/baseline render or spectrum. Use a disposable/checkpointed Disk project. After reopen, inspect returned mode/family/summary, render a controlled frequency sample or actual dialogue, compare spectrum/level, and check that prior gain/pan/pitch/fades were not removed. Audition the requested frequency and adjacent bands for the real creative result.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--preset` (optional, default: `"voice-presence-1k-6db"`)
- `--band` (optional) — EQ band index for supported parametric routes
- `--ui-band` (optional) — DaVinci Resolve clip EQ band label B1-B6
- `--filter-type` (optional) — bell, notch, high-shelf, low-shelf, high-pass, or low-pass
- `--freq` (optional) — EQ frequency in Hz for supported parametric routes
- `--gain-db` (optional) — EQ gain in dB for supported bell routes
- `--q` (optional) — EQ Q for supported parametric routes
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- `--band` and `--ui-band` are distinct address spaces and mutually exclusive.
- `--ui-band` 1 permits high-pass; B6 permits low-pass; middle bands do not.
- With no parameter options, `--preset` is used.
- The command targets one timeline audio row and does not affect all uses of a source or track EQ.
- Use `--at` for repeated names; it is record-domain time.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip audio-eq --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
