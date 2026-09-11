# `fairlight index tracks`

Syntax: `cutagent fairlight index tracks`

## Search terms

- list Fairlight audio tracks
- inventory timeline audio lanes
- count clips per audio track
- inspect track enabled and locked state
- show audio track format
- list stereo and mono tracks
- inspect Fairlight mixer overview
- find A1 A2 names
- audit Fairlight track heights
- map track index to name
- Fairlight Index track list

## What it does

List Fairlight Index audio tracks for the current timeline.

## Do not use when

Use narrow readers such as `fairlight mixer read`, `fairlight mixer fader`, `fairlight mixer pan`, or the track-display/info commands when a specific mix/display value must be authoritative; this command treats those as optional best-effort enrichments. Use `fairlight index markers` for timeline annotations, not track inventory.

## Preflight and readback

Afterward, treat absent optional fields or `available: false` as an instruction to run the corresponding narrow reader, not as a default value. No project-state verification is required because the command is read-only.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Optional mixer failures do not fail the command.
- It is saved UI state, not proof of current visible pixel height, and its presence does not imply that setting height is supported.
- Do not use this overview as sole proof before unlocking or enabling a track.
- Absence does not mean the track has Clear/default color.
- Global dry-run does not connect, count tracks, or exercise any optional reader.
- It returns `timeline: null` and only the intended target/tables.

## Examples

- `cutagent fairlight index tracks --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
