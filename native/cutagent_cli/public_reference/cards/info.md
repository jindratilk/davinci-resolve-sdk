# `info`

Syntax: `cutagent info`

## Search terms

- project and timeline summary
- timeline resolution and frame rate
- count timeline tracks
- how many timelines in project
- timeline start frame
- current project overview
- video audio subtitle track counts
- inspect open DaVinci Resolve project

## What it does

Read the DaVinci Resolve setup.

## Do not use when

Do not use it when the next edit depends on playhead, marks, current page, or current video item; use `context`. Do not treat project-level timeline settings as a complete per-timeline settings dump; use `timeline settings-get` or `project settings-get` for the exact key/value surface. Do not use track counts as evidence that a named track or clip exists; follow with `timeline track-list`, `timeline items`, or `clip list`.

## Preflight and readback

Run after `status` confirms the intended project, especially before creating a timeline, changing resolution/frame-rate settings, or adding/removing tracks. Use its current counts/settings as pre-state, perform the narrow mutation, then rerun `info` only when that mutation should change one of the fields reported here. For clip, grade, audio, or render changes, verify with the owning domain command instead.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- It cannot establish color management, audio sample rate, proxy settings, or other project configuration.

## Examples

- `cutagent info --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
