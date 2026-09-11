# `fairlight record stop`

Syntax: `cutagent fairlight record stop`

## Search terms

- stop Fairlight recording
- end audio capture
- stop voiceover take
- press stop while recording
- finish microphone recording
- stop current audio take
- end ADR recording
- stop recording now
- close current recorded take
- stop writing audio file
- terminate timeline audio recording

## What it does

Check Fairlight audio recording stop availability.

## Do not use when

This CLI error does not stop, pause, or finalize anything, so waiting for a retry can lengthen the take or continue writing disk data.
Use `fairlight record start` only to receive its separate unsupported start boundary, and `fairlight record arm` for the unsupported arm boundary.
Use timeline/media/file inspection to prove the resulting take was finalized and placed correctly.
Do not kill DaVinci Resolve or its process as a substitute for Stop because that risks an incomplete take/project state.

## Preflight and readback

Avoid switching projects/timelines, closing the application, unplugging the input, or killing a process while capture is active.
Audition it, save the project, and disarm the track if further recording is not intended.
After this CLI command's failure, assume recording state is unchanged.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- The command cannot distinguish “currently recording” from “already stopped.”
- The command cannot finalize, validate, rename, or recover a take file.
- It also cannot report whether a file was truncated or whether the disk filled.
- It does not disarm tracks, remove input monitoring, or reset patches after a manual stop; those are separate controls.
- It does not stop normal timeline playback, a render job, ADR cue playback, Sound Library audition, or external recorder hardware.

## Stable public error codes

- `CAPABILITY_NEGOTIATION_FAILED`

## Examples

- `cutagent fairlight record stop --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
