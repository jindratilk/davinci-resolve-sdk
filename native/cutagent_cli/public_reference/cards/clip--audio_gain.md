# `clip audio-gain`

Syntax: `cutagent clip audio-gain [NAME] --db VALUE [--at VALUE]`

## Search terms

- change one clip volume
- raise audio level on timeline clip
- lower clip gain
- make this clip louder
- attenuate linked audio occurrence
- adjust timeline item audio without track fader
- boost dialogue clip level

## What it does

Set linked audio gain.

## Do not use when

Use Fairlight track gain/fader commands when every clip routed through a track should change. Use `clip audio-normalize` when gain must be calculated from a measured peak, and `audio duck` when background material should vary under speech. Use media/source audio mapping commands to change channel interpretation. Do not use this command to alter a Media Pool master or all timeline instances; it targets one timeline audio row.

## Preflight and readback

Run `clip list`/`clip linked list` and provide `--at` when a name repeats. Capture an audio render or meter reading and inspect the existing clip effects/fades before writing. Use a disposable Disk project or checkpoint because the command closes/reopens the project. Afterward confirm the intended project/timeline/occurrence returned, render the exact clip span, and compare level numerically or by meters. Also check whether prior clip EQ, pan, pitch, or fade state survived.

## Public arguments and options

- `NAME` (optional) — Clip name
- `--db` (required) — Clip gain in dB
- `--at` (optional) — Record-domain position for deterministic clip selection

## Boundaries and gotchas

- A video-only clip or an unlinked occurrence without a resolvable audio companion fails.
- Repeated names require `--at` to avoid selecting the wrong occurrence.
- `--at` is record-domain time and includes timeline start offset conversion; it is not a source frame.
- In a 01:00:00:00 timeline, `--at 0f` selected the item at absolute frame 86400.

## Stable public error codes

- `VALIDATION_ERROR`

## Examples

- `cutagent clip audio-gain --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
