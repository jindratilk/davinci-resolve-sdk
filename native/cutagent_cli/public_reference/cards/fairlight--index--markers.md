# `fairlight index markers`

Syntax: `cutagent fairlight index markers`

## Search terms

- list Fairlight timeline markers
- show audio spotting markers
- inspect timeline notes
- list review cues
- find marker timecodes
- show Fairlight Index markers
- locate audio fix marker
- inventory timeline annotations
- get marker record frames
- list marker names and notes

## What it does

List Fairlight Index timeline markers.

## Do not use when

Use clip/media marker commands when the annotation belongs to a source or timeline item and must move with that clip. Use `fairlight index clips` to locate audio clip rows and `fairlight index tracks` for audio-track inventory. Use timeline marker add/delete/batch commands when mutation is intended; this command cannot filter or modify markers. Do not confuse markers with timeline in/out boundaries, keyframes, automation points, or subtitles.

## Preflight and readback

Before reading, activate the intended timeline and note its start timecode/frame rate if the distinction between relative and record positions matters. No post-mutation check is needed.

## Public arguments and options

This command has no command-specific arguments or options.

## Boundaries and gotchas

- Passing it to another command with ambiguous frame semantics can target the wrong location; choose the explicit field.
- A duration greater than one is reported but does not cause this command to expand the marker into per-frame rows.
- Global dry-run does not connect to DaVinci Resolve.
- These are timeline markers only.

## Examples

- `cutagent fairlight index markers --help`
  Expected: Shows the public syntax, arguments, options, and documented defaults.
