# `timeline stereo-convert`

Syntax: `cutagent timeline stereo-convert`

## Search terms

- convert timeline to stereo 3D
- ConvertTimelineToStereo
- stereoscopic timeline conversion
- make timeline stereoscopic
- DaVinci Resolve 3D timeline
- stereo eye timeline
- convert current timeline stereo

## What it does

Convert the current timeline to stereo 3D.

## Do not use when

Do not use this command to convert mono audio to stereo, change bus/track channel format, pan audio, create dual-mono tracks, or configure Fairlight output.
Do not run it on an important timeline without a duplicate/checkpoint and a manual plan for reversal. The command exposes no undo, reverse conversion, pre-state inspection, or post-conversion structural readback.

## Preflight and readback

Before execution, duplicate/checkpoint the project/timeline; activate the exact target; confirm that stereoscopic 3D conversion is intended; inspect existing stereo configuration, clips, grades, output monitoring, and delivery settings.
After execution, require `converted: true`, then inspect timeline stereo mode, left/right eye assignment, clip/link behavior, grades/effects, monitoring, and stereoscopic render output in DaVinci Resolve.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The only target is the current active timeline.
- It does not inspect eye assignments, stereo mode/settings, timeline items, grades, monitoring, or render output.
- It does not save the project.

## Stable public error codes

- `API_CALL_FAILED`

## Examples

- `cutagent timeline stereo-convert --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
