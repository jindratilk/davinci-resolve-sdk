# `audio reverb`

Syntax: `cutagent audio reverb INPUT [--output VALUE]`

## Search terms

- add echo to audio file
- make dialogue reverberant
- apply simple reverb
- create echoed audio copy
- ffmpeg aecho effect
- add room echo to source media
- preprocess audio with reverb
- render wet audio file

## What it does

Prepare reverb audio processing.

## Do not use when

Do not use `audio reverb` when the user wants an adjustable/non-destructive Fairlight reverb plugin on a clip, track, or bus; use the appropriate Fairlight/clip effect command. Do not use it when the processed file must automatically replace Media Pool media; unlike `audio duck --replace-media`, this command has no relink option. Do not present its fixed echo preset as a chosen room/acoustic match; there are no wet/dry, decay, room-size, or impulse-response controls.

## Preflight and readback

Run `audio info` on the input, choose an output outside user originals, and use global `--dry-run` to confirm the exact paths. After processing, run `audio info` on the output and listen/analyze the waveform because stream readability alone does not prove the artistic effect. If the user wants the result in the project, import or relink it explicitly and verify the Media Pool/timeline target afterward.

## Public arguments and options

- `INPUT` (required) — Input media file
- `--output/-o` (optional) — Output file

## Examples

- `cutagent audio reverb --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
